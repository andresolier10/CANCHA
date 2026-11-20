import os
import json
import secrets
import sqlite3
import time
from datetime import timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, request, session, g, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from sports import analyze, number, shootout_winner, normalize_position
from upgrade import register, insert_pairs

SPORTS = {'Fútbol 11': 11, 'Fútbol 7': 7, 'Futsal': 5, 'Baloncesto': 5}
POSITIONS = {'Portero', 'Defensa', 'Mediocampista', 'Delantero', 'Base', 'Escolta', 'Alero', 'Ala-pívot', 'Pívot'}


def create_app(database=None):
    app = Flask(__name__)
    root = Path(app.instance_path)
    root.mkdir(exist_ok=True)
    keyfile = root / 'secret.key'
    if not keyfile.exists():
        keyfile.write_text(secrets.token_hex(32))
    app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or keyfile.read_text(),
                      DATABASE=database or str(root / 'cancha.sqlite'),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('CANCHA_HTTPS') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024*1024)

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'])
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    def rows(sql, args=()):
        return [dict(r) for r in db().execute(sql, args).fetchall()]

    def one(sql, args=()):
        r = db().execute(sql, args).fetchone()
        return dict(r) if r else None

    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,version INTEGER DEFAULT 0,failures INTEGER DEFAULT 0,blocked REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tournaments(id INTEGER PRIMARY KEY,name TEXT NOT NULL,sport TEXT NOT NULL,format TEXT NOT NULL,capacity INTEGER NOT NULL,duration INTEGER NOT NULL,groups_count INTEGER DEFAULT 2,closed INTEGER DEFAULT 0,champion INTEGER);
        CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY,tournament_id INTEGER NOT NULL REFERENCES tournaments(id),name TEXT NOT NULL,group_no INTEGER DEFAULT 0,UNIQUE(tournament_id,name));
        CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY,team_id INTEGER NOT NULL REFERENCES teams(id),name TEXT NOT NULL,number INTEGER NOT NULL,position TEXT NOT NULL,UNIQUE(team_id,number));
        CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY,tournament_id INTEGER NOT NULL REFERENCES tournaments(id),home INTEGER NOT NULL REFERENCES teams(id),away INTEGER NOT NULL REFERENCES teams(id),round INTEGER NOT NULL,phase TEXT NOT NULL,group_no INTEGER DEFAULT 0,date TEXT DEFAULT '',hs INTEGER,aws INTEGER,hp INTEGER,ap INTEGER,winner INTEGER,events TEXT DEFAULT '[]',lineups TEXT DEFAULT '{}',metrics TEXT DEFAULT '{}');
        ''')
        db().commit()

    @app.teardown_appcontext
    def close(_):
        if 'db' in g:
            g.db.close()

    def fail(message, status=400):
        return jsonify(error=message), status

    @app.before_request
    def protect():
        g.user = None
        if session.get('uid'):
            user = one('SELECT * FROM users WHERE id=?', (session['uid'],))
            if user and user['version'] == session.get('version'):
                g.user = user
            else:
                session.clear()
        if request.method == 'POST':
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', secrets.token_hex())):
                return fail('La sesión del formulario venció. Recarga la página.', 403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def role(*allowed):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user or g.user['role'] not in allowed:
                    return fail('No tienes permisos para realizar esta operación.', 403)
                try:
                    if request.method == 'POST':
                        db().execute('BEGIN IMMEDIATE')
                    result = fn(*args, **kwargs)
                    db().commit()
                    return result
                except (ValueError, KeyError, TypeError) as e:
                    db().rollback()
                    return fail(str(e) or 'Revisa los campos.')
                except sqlite3.IntegrityError:
                    db().rollback()
                    return fail('El registro está duplicado o contiene referencias inválidas.')
            return wrapped
        return decorate

    def integer(value, low=0, high=999):
        if isinstance(value, bool) or str(value).strip() != str(int(value)) or not low <= int(value) <= high:
            raise ValueError(f'Ingresa un número entero entre {low} y {high}.')
        return int(value)

    def name(value):
        value = str(value).strip()
        if not 2 <= len(value) <= 100:
            raise ValueError('El nombre debe tener entre 2 y 100 caracteres.')
        return value

    def tournament(tid):
        t = one('SELECT * FROM tournaments WHERE id=?', (tid,))
        if not t:
            raise ValueError('No existe el torneo.')
        return t

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/session')
    def current_session():
        session.setdefault('csrf', secrets.token_hex(32))
        return jsonify(csrf=session['csrf'], user={k:g.user[k] for k in ('id','name','role')} if g.user else None,
                       setup=not one('SELECT id FROM users LIMIT 1'))

    @app.post('/api/setup')
    def setup():
        # First account is created locally; never expose an uninitialized server.
        if request.remote_addr not in ('127.0.0.1', '::1'):
            return fail('La configuración inicial requiere acceso local.',403)
        try:
            db().execute('BEGIN IMMEDIATE')
            if one('SELECT id FROM users LIMIT 1'):
                db().rollback()
                return fail('La cuenta administradora ya existe.',409)
            d = request.get_json()
            add_user(d, 'Administrador')
            db().commit()
            return jsonify(ok=True)
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as e:
            db().rollback()
            return fail(str(e))

    def add_user(d, user_role):
        if user_role not in ('Administrador','Empleado','Lector'):
            raise ValueError('Rol inválido.')
        email = str(d['email']).strip().lower()
        if '@' not in email or len(email)>254:
            raise ValueError('Correo inválido.')
        if not 10 <= len(d['password']) <= 128:
            raise ValueError('La contraseña debe tener entre 10 y 128 caracteres.')
        db().execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)',
                     (name(d['name']),email,generate_password_hash(d['password']),user_role))

    @app.post('/api/login')
    def login():
        d = request.get_json() or {}
        u = one('SELECT * FROM users WHERE email=?',(str(d.get('email','')).strip().lower(),))
        if u and u['blocked'] > time.time():
            return fail('Acceso bloqueado temporalmente. Intenta en 15 minutos.',429)
        if not u or not check_password_hash(u['password'],str(d.get('password',''))[:128]):
            if u:
                failures = u['failures']+1 if u['blocked']==0 else 1
                db().execute('UPDATE users SET failures=?,blocked=? WHERE id=?',(failures,time.time()+900 if failures>=5 else 0,u['id']))
                db().commit()
            return fail('Correo o contraseña incorrectos.',401)
        db().execute('UPDATE users SET failures=0,blocked=0 WHERE id=?',(u['id'],))
        db().commit()
        session.clear()
        session.update(uid=u['id'],version=u['version'],csrf=secrets.token_hex(32))
        session.permanent=True
        return jsonify(ok=True)

    @app.post('/api/logout')
    def logout():
        if g.user:
            db().execute('UPDATE users SET version=version+1 WHERE id=?',(g.user['id'],))
            db().commit()
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/users')
    @role('Administrador')
    def users():
        return jsonify(rows('SELECT id,name,email,role FROM users'))

    @app.post('/api/users')
    @role('Administrador')
    def new_user():
        d=request.get_json()
        add_user(d,d['role'])
        return jsonify(ok=True)

    @app.post('/api/users/<int:uid>/role')
    @role('Administrador')
    def change_role(uid):
        r=request.get_json()['role']
        if uid==g.user['id'] or r not in ('Administrador','Empleado','Lector'):
            raise ValueError('No puedes cambiar tu propio rol o usar un rol inválido.')
        db().execute('UPDATE users SET role=?,version=version+1 WHERE id=?',(r,uid))
        return jsonify(ok=True)

    @app.get('/api/tournaments')
    def tournaments():
        return jsonify(rows('SELECT t.*, (SELECT count(*) FROM teams WHERE tournament_id=t.id) AS teams_count FROM tournaments t ORDER BY id DESC'))

    @app.post('/api/tournaments')
    @role('Administrador')
    def create_tournament():
        d=request.get_json()
        sport=d['sport']; fmt=d['format']
        if sport not in SPORTS or fmt not in ('Liga','Fase liguera + eliminatorias','Grupos','Eliminación directa'):
            raise ValueError('Deporte o formato inválido.')
        cap=integer(d['capacity'],2,32)
        legs=integer(d.get('legs',1),1,2) if fmt!='Eliminación directa' else 1
        qualifiers=integer(d.get('qualifiers', min(4,cap)),2,cap) if fmt=='Fase liguera + eliminatorias' else min(4,cap)
        start=str(d.get('start_date',''))
        if start:
            from datetime import datetime
            datetime.fromisoformat(start)
        gap=integer(d.get('gap_days',7),1,90) if start and fmt!='Eliminación directa' else 7
        groups=integer(d.get('groups_count',2),2,8) if fmt=='Grupos' else 2
        if fmt=='Grupos' and (cap % groups or cap//groups<2 or groups not in (2,4,8)):
            raise ValueError('Usa 2, 4 u 8 grupos con igual número de equipos, al menos 2 por grupo.')
        group_qualifiers=integer(d.get('group_qualifiers',2),1,cap//groups) if fmt=='Grupos' else 2
        c=db().execute('INSERT INTO tournaments(name,sport,format,capacity,duration,groups_count,legs,qualifiers,start_date,gap_days,group_qualifiers) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (name(d['name']),sport,fmt,cap,integer(d['duration'],10,120),groups,legs,qualifiers,start,gap,group_qualifiers))
        return jsonify(id=c.lastrowid)

    def standings(tid):
        ts=rows('SELECT * FROM teams WHERE tournament_id=?',(tid,))
        table={t['id']:dict(t,pj=0,pg=0,pe=0,pp=0,gf=0,gc=0,dg=0,pts=0) for t in ts}
        basket=tournament(tid)['sport']=='Baloncesto'
        for m in rows("SELECT * FROM matches WHERE tournament_id=? AND hs IS NOT NULL AND phase!='Llave'",(tid,)):
            for a,b,s,c in ((m['home'],m['away'],m['hs'],m['aws']),(m['away'],m['home'],m['aws'],m['hs'])):
                r=table[a];r['pj']+=1;r['gf']+=s;r['gc']+=c;r['dg']=r['gf']-r['gc']
                r['pg']+=s>c;r['pe']+=s==c;r['pp']+=s<c
                r['pts']+=(2 if basket else 3) if s>c else (1 if s==c or basket else 0)
        return sorted(table.values(),key=lambda x:(x['group_no'],-x['pts'],-x['dg'],-x['gf'],x['name']))

    @app.get('/api/tournaments/<int:tid>')
    def detail(tid):
        t=one('SELECT * FROM tournaments WHERE id=?',(tid,))
        if not t:return fail('Torneo no encontrado.',404)
        ms=rows("SELECT m.*, h.name home_name,a.name away_name FROM matches m JOIN teams h ON h.id=m.home JOIN teams a ON a.id=m.away WHERE m.tournament_id=? ORDER BY CASE WHEN m.phase='Llave' THEN 1 ELSE 0 END,m.round,m.group_no,m.id",(tid,))
        ps=rows('SELECT p.*,t.name team_name FROM players p JOIN teams t ON p.team_id=t.id WHERE t.tournament_id=?',(tid,))
        totals={p['id']:dict(p,goals=0,assists=0,yellows=0,reds=0,points=0) for p in ps}
        for m in ms:
            for k in ('events','lineups','metrics','squads','formations'):m[k]=json.loads(m[k])
            # Compatibilidad con actas creadas antes de incluir las convocatorias.
            if not m['squads'] and m['lineups']:
                m['squads']={str(tm):[p['id'] for p in ps if p['team_id']==tm] for tm in (m['home'],m['away'])}
            try:
                m['analysis']=analyze(t['sport'],t['duration'],[m['home'],m['away']],
                                      [p for p in ps if p['team_id'] in (m['home'],m['away'])],m['squads'],m['lineups'],m['events'])
            except ValueError:
                m['analysis']=None
            for e in m['events']:
                p=totals.get(e.get('player'))
                if p:
                    key={'Gol':'goals','Penal':'goals','Asistencia':'assists','Amarilla':'yellows','Roja':'reds','Punto':'points'}.get(e['type'])
                    if key:p[key]+=e.get('value',1) if e['type']=='Punto' else 1
        return jsonify(tournament=t,teams=rows('SELECT * FROM teams WHERE tournament_id=?',(tid,)),players=ps,matches=ms,standings=standings(tid) if t['format']!='Eliminación directa' else [],statistics=list(totals.values()))

    @app.post('/api/tournaments/<int:tid>/teams')
    @role('Administrador','Empleado')
    def team(tid):
        t=tournament(tid)
        if one('SELECT id FROM matches WHERE tournament_id=?',(tid,)):
            raise ValueError('La inscripción se cerró al generar la programación.')
        if one('SELECT count(*) n FROM teams WHERE tournament_id=?',(tid,))['n']>=t['capacity']:
            raise ValueError('El torneo ya completó su capacidad.')
        db().execute('INSERT INTO teams(tournament_id,name) VALUES(?,?)',(tid,name(request.get_json()['name'])))
        return jsonify(ok=True)

    @app.post('/api/teams/<int:teamid>/players')
    @role('Administrador','Empleado')
    def players(teamid):
        tm=one('SELECT * FROM teams WHERE id=?',(teamid,))
        if not tm:raise ValueError('Equipo inválido.')
        sport=tournament(tm['tournament_id'])['sport']
        valid={'Base','Escolta','Alero','Ala-pívot','Pívot'} if sport=='Baloncesto' else {'Portero','Defensa','Mediocampista','Delantero'}
        batch=request.get_json()['players']
        if not 1<=len(batch)<=30:raise ValueError('Registra de 1 a 30 jugadores por envío.')
        for index,p in enumerate(batch,1):
            label=str(p.get('name','')).strip() or 'Jugador sin nombre'
            try:
                player_name=name(p.get('name',''))
                position=normalize_position(p.get('position'),valid)
                try: dorsal=integer(p.get('number'),0,99)
                except (TypeError,ValueError): raise ValueError('El dorsal debe ser un entero entre 0 y 99.')
                existing=one('SELECT name FROM players WHERE team_id=? AND number=?',(teamid,dorsal))
                if existing: raise ValueError(f"El dorsal {dorsal} ya pertenece a {existing['name']}.")
                db().execute('INSERT INTO players(team_id,name,number,position) VALUES(?,?,?,?)',(teamid,player_name,dorsal,position))
            except ValueError as error:
                raise ValueError(f'{label}: {error}')
        return jsonify(ok=True)

    @app.post('/api/teams/<int:teamid>/players/edit')
    @role('Administrador','Empleado')
    def edit_players(teamid):
        tm=one('SELECT * FROM teams WHERE id=?',(teamid,))
        if not tm: raise ValueError('Equipo inválido.')
        sport=tournament(tm['tournament_id'])['sport']
        valid={'Base','Escolta','Alero','Ala-pívot','Pívot'} if sport=='Baloncesto' else {'Portero','Defensa','Mediocampista','Delantero'}
        existing=rows('SELECT * FROM players WHERE team_id=?',(teamid,))
        original={p['id']:p for p in existing}
        batch=request.get_json().get('players',[])
        updates={}; numbers={}
        for i,p in enumerate(batch,1):
            pid=integer(p.get('id'),1,1000000000)
            if pid not in original or pid in updates: raise ValueError('Jugador ajeno al equipo o repetido.')
            label=p.get('name') or original[pid]['name']
            try:
                pname=name(p.get('name',''))
                try: dorsal=integer(p.get('number'),0,99)
                except (ValueError,TypeError): raise ValueError('El dorsal debe ser un entero entre 0 y 99.')
                position=normalize_position(p.get('position'),valid)
                # Evita sobrescribir una edición guardada desde otra pestaña.
                previous=p.get('original')
                if previous is not None and any(previous.get(k)!=original[pid][k] for k in ('name','number','position')):
                    raise ValueError('Este jugador cambió en otra pestaña. Cierra y vuelve a abrir la plantilla.')
                updates[pid]=dict(name=pname,number=dorsal,position=position)
            except ValueError as error: raise ValueError(f'{label}: {error}')
        for p in existing:
            updated=updates.get(p['id'],p); dorsal=updated['number']
            if dorsal in numbers: raise ValueError(f"Dorsal {dorsal} repetido: {numbers[dorsal]} y {updated['name']}.")
            numbers[dorsal]=updated['name']
        # Dorsales temporales únicos permiten intercambiarlos sin borrar jugadores.
        occupied={p['number'] for p in existing}; temporary=-1
        for pid in updates:
            while temporary in occupied: temporary-=1
            db().execute('UPDATE players SET number=? WHERE id=?',(temporary,pid))
            occupied.add(temporary);temporary-=1
        for pid,p in updates.items():
            db().execute('UPDATE players SET name=?,number=?,position=? WHERE id=?',(p['name'],p['number'],p['position'],pid))
        return jsonify(ok=True)

    def league(tid,ids,group=0,legs=1):
        ids=list(ids)
        if len(ids)%2:ids.append(None)
        for r in range(1,len(ids)):
            for a,b in zip(ids[:len(ids)//2],reversed(ids[len(ids)//2:])):
                if a and b:db().execute('INSERT INTO matches(tournament_id,home,away,round,phase,group_no) VALUES(?,?,?,?,?,?)',(tid,a,b,r,'Grupo' if group else 'Liga',group))
                if a and b and legs==2:db().execute('INSERT INTO matches(tournament_id,home,away,round,phase,group_no) VALUES(?,?,?,?,?,?)',(tid,b,a,r+len(ids)-1,'Grupo' if group else 'Liga',group))
            ids=[ids[0],ids[-1]]+ids[1:-1]

    def bracket(tid,ids,r):
        # Byes are carried forward; real fixtures never reference a placeholder team.
        power=1
        while power<len(ids):power*=2
        byes=power-len(ids)
        pairs=[[x,None] for x in ids[:byes]]+[[ids[i],ids[i+1]] for i in range(byes,len(ids),2)]
        insert_pairs(db,tid,ids,pairs,r)
        return ids[:byes]

    @app.post('/api/tournaments/<int:tid>/schedule')
    @role('Administrador')
    def schedule(tid):
        t=tournament(tid)
        ts=rows('SELECT * FROM teams WHERE tournament_id=? ORDER BY id',(tid,))
        if one('SELECT id FROM matches WHERE tournament_id=?',(tid,)):raise ValueError('La programación ya existe.')
        if len(ts)!=t['capacity']:raise ValueError('Completa todos los equipos antes de generar la programación.')
        for tm in ts:
            n=one('SELECT count(*) n FROM players WHERE team_id=?',(tm['id'],))['n']
            if n<SPORTS[t['sport']]:raise ValueError(f"{tm['name']}: requiere al menos {SPORTS[t['sport']]} jugadores.")
        ids=[tm['id'] for tm in ts]
        if t['format'] in ('Liga','Fase liguera + eliminatorias'):league(tid,ids,legs=t['legs'])
        elif t['format']=='Grupos':
            for group in range(t['groups_count']):
                members=ids[group::t['groups_count']]
                for member in members:db().execute('UPDATE teams SET group_no=? WHERE id=?',(group+1,member))
                league(tid,members,group+1,t['legs'])
        else:
            import random
            random.SystemRandom().shuffle(ids)
            bracket(tid,ids,1)
        if t['start_date']:
            from datetime import datetime
            start=datetime.fromisoformat(t['start_date'])
            for match in rows('SELECT id,round FROM matches WHERE tournament_id=?',(tid,)):
                date=start+timedelta(days=(match['round']-1)*t['gap_days'])
                db().execute('UPDATE matches SET date=? WHERE id=?',(date.isoformat(timespec='minutes'),match['id']))
        return jsonify(ok=True)

    @app.post('/api/tournaments/<int:tid>/advance')
    @role('Administrador')
    def advance(tid):
        t=tournament(tid)
        d=request.get_json() or {}
        ms=rows("SELECT * FROM matches WHERE tournament_id=? AND phase='Llave' ORDER BY id",(tid,))
        ms=[dict(m, winner=m['tie_winner'] if m['two_legs'] else m['winner']) for m in ms if not m['return_of']]
        if t['champion']:raise ValueError('El torneo ya tiene campeón.')
        def ordered_table():
            table=standings(tid)
            order=d.get('order',[])
            if any((a['pts'],a['dg'],a['gf'])==(b['pts'],b['dg'],b['gf']) for a,b in zip(table,table[1:])):
                if set(order)!=set(x['id'] for x in table) or len(order)!=len(table):
                    raise ValueError('Hay equipos empatados. Ordena sus nombres en el apartado de desempate antes de confirmar.')
                table.sort(key=lambda x:(-x['pts'],-x['dg'],-x['gf'],order.index(x['id'])))
            return table
        if not ms and t['format'] in ('Liga','Fase liguera + eliminatorias'):
            games=rows('SELECT * FROM matches WHERE tournament_id=?',(tid,))
            if not games or any(m['hs'] is None for m in games):raise ValueError('Completa todos los partidos de la fase liguera.')
            table=ordered_table()
            if t['format']=='Liga':
                db().execute('UPDATE tournaments SET champion=?,closed=1 WHERE id=?',(table[0]['id'],tid))
            else:
                ids=[x['id'] for x in table[:t['qualifiers']]]
                db().execute('UPDATE tournaments SET qualified_ids=? WHERE id=?',(json.dumps(ids),tid))
                if d.get('pairs'):insert_pairs(db,tid,ids,d['pairs'],1)
                else:bracket(tid,ids,1)
                db().execute('UPDATE tournaments SET closed=1 WHERE id=?',(tid,))
            return jsonify(ok=True)
        if not ms:
            if t['format']!='Grupos':raise ValueError('No hay una fase para avanzar.')
            gs=rows('SELECT * FROM matches WHERE tournament_id=?',(tid,))
            if not gs or any(m['hs'] is None for m in gs):raise ValueError('Completa todos los partidos de grupos.')
            table=standings(tid); groups=[]
            per_group=integer(d.get('group_qualifiers',t['group_qualifiers']),1,t['capacity']//t['groups_count'])
            order=request.get_json().get('order',[])
            for group in range(1,t['groups_count']+1):
                rs=[r for r in table if r['group_no']==group]
                tied=any((a['pts'],a['dg'],a['gf'])==(b['pts'],b['dg'],b['gf']) for a,b in zip(rs,rs[1:]))
                if tied:
                    if set(order)!=set(x['id'] for x in table) or len(order)!=len(table):raise ValueError('Hay equipos empatados dentro de un grupo. Ordena sus nombres antes de clasificar.')
                    rs.sort(key=lambda x:(-x['pts'],-x['dg'],-x['gf'],order.index(x['id'])))
                groups.append(rs[:per_group])
            ids=[]
            # Empareja grupos vecinos e invierte el orden del segundo grupo.
            for i in range(0,len(groups),2):
                for rank in range(per_group):ids.extend([groups[i][rank]['id'],groups[i+1][per_group-1-rank]['id']])
            db().execute('UPDATE tournaments SET qualified_ids=?,group_qualifiers=? WHERE id=?',(json.dumps(ids),per_group,tid))
            if d.get('pairs'):insert_pairs(db,tid,ids,d['pairs'],1)
            else:bracket(tid,ids,1)
            db().execute('UPDATE tournaments SET closed=1 WHERE id=?',(tid,))
        else:
            r=max(m['round'] for m in ms);last=[m for m in ms if m['round']==r]
            if any(m['winner'] is None for m in last):raise ValueError('Completa los partidos de la ronda actual.')
            ids=[m['winner'] for m in last]
            saved_rounds=json.loads(t['bracket_rounds'])
            if str(r) in saved_rounds:
                ids=[]
                for a,b in saved_rounds[str(r)]:
                    ids.append(a if b is None else next(m['winner'] for m in last if m['home']==a and m['away']==b))
            elif r==1:
                used={m[k] for m in last for k in ('home','away')}
                eligible=(json.loads(t['qualified_ids']) if t['format'] in ('Fase liguera + eliminatorias','Grupos') and json.loads(t['qualified_ids']) else [x['id'] for x in rows('SELECT id FROM teams WHERE tournament_id=? ORDER BY id',(tid,))] if t['format']=='Eliminación directa' else list(used))
                ids=[x for x in eligible if x not in used]+ids
            if len(ids)==1:db().execute('UPDATE tournaments SET champion=? WHERE id=?',(ids[0],tid))
            elif d.get('pairs'):insert_pairs(db,tid,ids,d['pairs'],r+1)
            else:bracket(tid,ids,r+1)
        return jsonify(ok=True)

    @app.post('/api/matches/<int:mid>/two-legs')
    @role('Administrador','Empleado')
    def configure_legs(mid):
        m=one('SELECT * FROM matches WHERE id=?',(mid,))
        if not m or m['phase']!='Llave' or m['return_of']:raise ValueError('Selecciona un cruce de eliminación directa.')
        t=tournament(m['tournament_id'])
        if t['sport']=='Baloncesto':raise ValueError('Ida y vuelta está disponible para fútbol y futsal.')
        if t['champion'] or one('SELECT id FROM matches WHERE tournament_id=? AND hs IS NOT NULL',(t['id'],)) or one("SELECT id FROM matches WHERE tournament_id=? AND phase='Llave' AND round>?",(t['id'],m['round'])):raise ValueError('Elige ida y vuelta antes de registrar el primer resultado del cruce.')
        enabled=bool(request.get_json().get('enabled'))
        child=one('SELECT * FROM matches WHERE return_of=?',(mid,))
        if child and child['hs'] is not None:raise ValueError('La vuelta ya tiene resultado.')
        if enabled and not child:
            db().execute("INSERT INTO matches(tournament_id,home,away,round,phase,return_of) VALUES(?,?,?,?, 'Llave',?)",(t['id'],m['away'],m['home'],m['round'],mid))
        if not enabled:db().execute('DELETE FROM matches WHERE return_of=?',(mid,))
        db().execute('UPDATE matches SET two_legs=?,tie_winner=NULL WHERE id=?',(int(enabled),mid))
        return jsonify(ok=True)

    @app.post('/api/matches/<int:mid>')
    @role('Administrador','Empleado')
    def result(mid):
        m=one('SELECT * FROM matches WHERE id=?',(mid,))
        if not m:raise ValueError('Partido inválido.')
        t=tournament(m['tournament_id']);d=request.get_json();basket=t['sport']=='Baloncesto'
        if t['champion'] or (m['phase'] in ('Grupo','Liga') and t['closed']) or (m['phase']=='Llave' and one("SELECT id FROM matches WHERE tournament_id=? AND phase='Llave' AND round>?",(t['id'],m['round']))):
            raise ValueError('Esta fase está cerrada; no admite correcciones.')
        hs=integer(d['hs']);aws=integer(d['aws']);hp=ap=None
        first=one('SELECT * FROM matches WHERE id=?',(m['return_of'],)) if m['return_of'] else None
        if first and first['hs'] is None:raise ValueError('Registra primero el resultado de la ida.')
        if m['two_legs'] and one('SELECT id FROM matches WHERE return_of=? AND hs IS NOT NULL',(mid,)):raise ValueError('La vuelta ya está registrada; no puedes cambiar la ida.')
        gh=hs+(first['aws'] if first else 0);ga=aws+(first['hs'] if first else 0)
        decisive=not m['two_legs']
        winner=m['home'] if hs>aws else m['away'] if aws>hs else None
        tie_winner=m['home'] if gh>ga else m['away'] if ga>gh else None
        if winner is None and basket:raise ValueError('Baloncesto requiere un ganador después de las prórrogas.')
        if tie_winner is None and decisive and m['phase']=='Llave' and not any(e.get('type')=='Penal de tanda' for e in d.get('events',[])):
            raise ValueError('El partido de eliminación está empatado. Registra cada cobrador y si convirtió o falló en la tanda de penales.')
        date=str(d.get('date',''))
        if date:
            from datetime import datetime
            datetime.fromisoformat(date)
        roster=rows('SELECT * FROM players WHERE team_id IN (?,?)',(m['home'],m['away']))
        lineups=d.get('lineups',{}); events=d.get('events',[])
        squads=d.get('squads')
        if squads is None:
            squads={str(tm):[p['id'] for p in roster if p['team_id']==tm] for tm in (m['home'],m['away'])} if lineups else {}
        analysis=analyze(t['sport'],t['duration'],[m['home'],m['away']],roster,squads,lineups,events)
        key='points' if basket else 'goals'
        if any(e['type']!='Penal de tanda' for e in events) and (analysis['teams'][str(m['home'])][key]!=hs or analysis['teams'][str(m['away'])][key]!=aws):
            raise ValueError('Las anotaciones de los jugadores deben coincidir con el marcador. Cada gol o penal convertido cuenta como un remate: no lo registres dos veces.')
        if any(e['type']=='Penal de tanda' for e in events):
            if m['phase']!='Llave' or not decisive or gh!=ga: raise ValueError('La tanda solo se registra en la vuelta con global empatado, o en un partido único empatado.')
            w=shootout_winner(analysis['teams'],[m['home'],m['away']])
            if not w: raise ValueError('La tanda no ha definido ganador.')
            hp=analysis['teams'][str(m['home'])]['shootout_scored'];ap=analysis['teams'][str(m['away'])]['shootout_scored'];tie_winner=int(w)
            if not first:winner=int(w)
        metrics=d.get('metrics',{})
        possession=[metrics.get(str(team),{}).get('possession') for team in (m['home'],m['away'])]
        if any(x is not None for x in possession):
            if any(x is None for x in possession) or sum(integer(x,0,100) for x in possession)!=100:raise ValueError('La posesión de ambos equipos debe sumar 100 %.')
        for teamid in (m['home'],m['away']):
            stats=metrics.get(str(teamid),{})
            for key,value in stats.items():integer(value)
            if 'completed_passes' in stats and ('passes' in stats and stats['completed_passes']>stats['passes']):raise ValueError('Los pases completados de un equipo no pueden superar sus propios pases totales. No se comparan con los pases del rival.')
            if stats.get('al_arco',0)>stats.get('remates',0):raise ValueError('Los remates al arco no pueden superar los remates totales.')
            if events:
                a=analysis['teams'][str(teamid)]
                stats.update(remates=a['shots'],al_arco=a['on_target'],faltas=a['fouls'],entradas=a['tackles'],ocasiones_falladas=a['big_misses'],amarillas=a['yellows'],rojas=a['reds'])
                metrics[str(teamid)]=stats
        db().execute('UPDATE matches SET hs=?,aws=?,hp=?,ap=?,winner=?,date=?,events=?,lineups=?,metrics=?,squads=?,formations=? WHERE id=?',
                     (hs,aws,hp,ap,winner,date,json.dumps(analysis['events']),json.dumps(lineups),json.dumps(metrics),json.dumps(squads),json.dumps(d.get('formations',{})),mid))
        if first:db().execute('UPDATE matches SET tie_winner=? WHERE id=?',(tie_winner,first['id']))
        return jsonify(ok=True)

    register(app,db,rows,one,role,tournament,standings,league,bracket)
    return app


if __name__=='__main__':
    create_app().run(host='127.0.0.1',port=int(os.getenv('PORT',5000)),debug=False)
