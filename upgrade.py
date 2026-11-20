"""Calendarios, clasificación y centro de partidos independiente."""
import json
import math
import time
from datetime import datetime, timedelta
from sports import analyze, number, SIZES, shootout_winner, normalize_position
from flask import request, jsonify, g


def register(app, db, rows, one, role, tournament, standings, league, bracket):
    with app.app_context():
        additions = {
            'tournaments': {'legs': 'INTEGER DEFAULT 1', 'qualifiers': 'INTEGER DEFAULT 4', 'start_date': "TEXT DEFAULT ''", 'gap_days': 'INTEGER DEFAULT 7', 'qualified_ids': "TEXT DEFAULT '[]'", 'group_qualifiers':'INTEGER DEFAULT 2','bracket_rounds':"TEXT DEFAULT '{}'",'leg_plan':"TEXT DEFAULT '[]'"},
            'matches': {'squads': "TEXT DEFAULT '{}'", 'formations': "TEXT DEFAULT '{}'", 'slot':'INTEGER', 'return_of':'INTEGER', 'two_legs':'INTEGER DEFAULT 0', 'tie_winner':'INTEGER'},
        }
        for table, columns in additions.items():
            existing = {r['name'] for r in rows(f'PRAGMA table_info({table})')}
            for column, declaration in columns.items():
                if column not in existing: db().execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')
        db().execute('CREATE TABLE IF NOT EXISTS live_series(id INTEGER PRIMARY KEY, title TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0)')
        db().commit()

    def get_series(sid):
        record = one('SELECT * FROM live_series WHERE id=?', (sid,))
        if not record: raise ValueError('Encuentro no encontrado.')
        return record, json.loads(record['payload'])

    def calculated(s, leg):
        return analyze(s['sport'], s['duration'], ['a', 'b'], s['players'], leg['squads'], leg['lineups'], leg['events'], leg['status'] != 'Programado')

    def pack(record, s):
        result = dict(s, id=record['id'], revision=record['revision'], server_time=time.time())
        result['legs'] = [dict(leg, analysis=calculated(s, leg)) for leg in s['legs']]
        return result

    @app.get('/api/live')
    def live_list():
        result=[]
        for r in rows('SELECT * FROM live_series ORDER BY id DESC'):
            s=json.loads(r['payload'])
            result.append(dict(id=r['id'], title=r['title'], sport=s['sport'], teams=s['teams'],
                               dates=[l['date'] for l in s['legs']], statuses=[l['status'] for l in s['legs']], winner=s.get('winner')))
        return jsonify(result)

    @app.post('/api/live')
    @role('Administrador', 'Empleado')
    def create_live():
        d=request.get_json()
        sport=d.get('sport', 'Fútbol 11')
        if sport not in SIZES: raise ValueError('Deporte no válido.')
        names=[str(d.get(k, '')).strip() for k in ('home','away')]
        if any(not 2 <= len(n) <= 100 for n in names) or names[0].casefold()==names[1].casefold():
            raise ValueError('Escribe dos equipos diferentes, entre 2 y 100 caracteres.')
        legs=number(d.get('legs', 2), 1, 2)
        dates=d.get('dates', ['', ''])
        for date in dates:
            if date: datetime.fromisoformat(date)
        s=dict(title=' vs. '.join(names), sport=sport, duration=number(d.get('duration',90),10,120),
               teams={'a':names[0], 'b':names[1]}, players=[], legs=[], audit=[], winner=None)
        for i in range(legs):
            s['legs'].append(dict(home='a' if i==0 else 'b', away='b' if i==0 else 'a', date=dates[i] if i<len(dates) else '',
                                  squads={}, lineups={}, formations={}, events=[], status='Programado', clock_elapsed=0, clock_started=None))
        c=db().execute('INSERT INTO live_series(title,payload) VALUES(?,?)',(s['title'],json.dumps(s)))
        return jsonify(id=c.lastrowid)

    @app.get('/api/live/<int:sid>')
    def read_live(sid):
        try:
            r,s=get_series(sid)
            return jsonify(pack(r,s))
        except ValueError as e: return jsonify(error=str(e)),404

    @app.post('/api/live/<int:sid>/action')
    @role('Administrador', 'Empleado')
    def live_action(sid):
        r,s=get_series(sid); d=request.get_json()
        if d.get('revision') != r['revision']:
            return jsonify(error='Otro registro cambió este encuentro. Actualiza el panel antes de continuar.'),409
        idx=number(d.get('leg',0),0,len(s['legs'])-1); leg=s['legs'][idx]; action=d.get('action')
        if action=='roster':
            if any(l['status']!='Programado' for l in s['legs']): raise ValueError('La plantilla se cierra al comenzar la serie.')
            ps=d['players']; seen=set(); players=[]
            if not isinstance(ps,list) or len(ps)>120: raise ValueError('Máximo 60 jugadores por equipo.')
            valid={'Base','Escolta','Alero','Ala-pívot','Pívot'} if s['sport']=='Baloncesto' else {'Portero','Defensa','Mediocampista','Delantero'}
            for i,p in enumerate(ps):
                tid=p.get('team_id'); name=str(p.get('name','')).strip()
                label=f"{s['teams'].get(tid,'Equipo desconocido')} · {name or 'Jugador sin nombre'}"
                try:
                    if tid not in ('a','b') or not 2<=len(name)<=100: raise ValueError('El nombre debe tener entre 2 y 100 caracteres.')
                    try: num=number(p.get('number'),0,99)
                    except (TypeError,ValueError): raise ValueError('El dorsal debe ser un entero entre 0 y 99.')
                    position=normalize_position(p.get('position'),valid)
                    if (tid,num) in seen: raise ValueError(f'El dorsal {num} está repetido en este equipo.')
                    seen.add((tid,num)); players.append(dict(id=i+1,team_id=tid,name=name,number=num,position=position))
                except ValueError as error:
                    raise ValueError(f'{label}: {error}')
            s['players']=players
            for l in s['legs']: l.update(squads={},lineups={})
        elif action=='lineup':
            if leg['status']!='Programado': raise ValueError('Los titulares se fijan antes de iniciar el partido.')
            leg['squads']=d['squads']; leg['lineups']=d['lineups']
            leg['formations']=d.get('formations',{})
            analyze(s['sport'],s['duration'],['a','b'],s['players'],leg['squads'],leg['lineups'],[],True)
        elif action=='date':
            if leg['status']!='Programado': raise ValueError('El partido ya comenzó.')
            if d['date']: datetime.fromisoformat(d['date'])
            leg['date']=d['date']
        elif action=='event':
            if leg['status'] not in ('En vivo','Pausado'): raise ValueError('Inicia el partido antes de registrar eventos.')
            leg['events'].append(d['event'])
            leg['events']=calculated(s,leg)['events']
        elif action=='undo':
            if leg['status'] not in ('En vivo','Pausado') or not leg['events']: raise ValueError('No hay un último evento editable.')
            reason=str(d.get('reason','')).strip()
            if len(reason)<3: raise ValueError('Indica el motivo de la corrección.')
            s['audit'].append(dict(event=leg['events'].pop(),reason=reason[:300],user=g.user['name'],time=time.time(),leg=idx))
        elif action=='clock':
            if leg['status'] not in ('En vivo','Pausado'): raise ValueError('El reloj se ajusta durante el partido.')
            seconds=number(d['seconds'],0,(s['duration']+180)*60)
            if leg['events'] and seconds < leg['events'][-1]['minute']*60+leg['events'][-1].get('second',0):
                raise ValueError('El reloj no puede quedar antes del último evento registrado.')
            leg['clock_elapsed']=seconds
            leg['clock_started']=time.time() if leg['status']=='En vivo' else None
        elif action=='status':
            status=d['status']
            allowed={'Programado':['En vivo'],'En vivo':['Pausado','Finalizado'],'Pausado':['En vivo','Finalizado'],'Finalizado':[]}
            if status not in allowed[leg['status']]: raise ValueError('Cambio de estado no permitido.')
            if idx==1 and s['legs'][0]['status']!='Finalizado': raise ValueError('Finaliza la ida antes de comenzar la vuelta.')
            analyze(s['sport'],s['duration'],['a','b'],s['players'],leg['squads'],leg['lineups'],leg['events'],True)
            if leg['clock_started'] is not None:
                leg['clock_elapsed']+=max(0,time.time()-leg['clock_started'])
            leg.update(status=status,clock_started=time.time() if status=='En vivo' else None)
            if status=='Finalizado':
                stat=calculated(s,leg)['teams']; key='points' if s['sport']=='Baloncesto' else 'goals'
                if s['sport']=='Baloncesto' and stat['a'][key]==stat['b'][key]: raise ValueError('Juega la prórroga: baloncesto no admite empate.')
                if any(e['type']=='Penal de tanda' for e in leg['events']) and idx!=len(s['legs'])-1: raise ValueError('La tanda se cobra al final de la serie.')
                if idx==len(s['legs'])-1:
                    total={t:sum(calculated(s,l)['teams'][t][key] for l in s['legs']) for t in ('a','b')}
                    penalty=any(e['type']=='Penal de tanda' for e in leg['events'])
                    if penalty and total['a']!=total['b']: raise ValueError('Solo puede haber tanda cuando el global está empatado.')
                    winner='a' if total['a']>total['b'] else 'b' if total['b']>total['a'] else None
                    if penalty:
                        winner=shootout_winner(stat,['a','b'])
                        if not winner: raise ValueError('La tanda todavía no tiene un ganador reglamentario.')
                    s['winner']=winner
        else: raise ValueError('Acción desconocida.')
        db().execute('UPDATE live_series SET payload=?,revision=revision+1 WHERE id=?',(json.dumps(s),sid))
        return jsonify(ok=True)

    @app.get('/api/live/<int:sid>/prediction')
    def prediction(sid):
        try: r,s=get_series(sid)
        except ValueError as e: return jsonify(error=str(e)),404
        if s['sport']=='Baloncesto':
            return jsonify(available=False,reason='La estimación de marcadores está diseñada para fútbol. Se mantienen todas las estadísticas de baloncesto.')
        samples={t:[] for t in ('a','b')}; names={t:s['teams'][t].casefold().strip() for t in ('a','b')}
        # Solo encuentros finalizados: evita presentar unos minutos de juego como un partido completo.
        for record in rows('SELECT * FROM live_series ORDER BY id DESC'):
            other=json.loads(record['payload'])
            if other['sport']!=s['sport']: continue
            for l in reversed(other['legs']):
                if l['status']!='Finalizado': continue
                a=calculated(other,l)['teams']
                for target in ('a','b'):
                    for tid in ('a','b'):
                        if other['teams'][tid].casefold().strip()==names[target]:
                            rival='b' if tid=='a' else 'a'
                            samples[target].append(dict(gf=a[tid]['goals'],ga=a[rival]['goals'],shots=a[tid]['shots'],cards=a[tid]['yellows']+a[tid]['reds'],fouls=a[tid]['fouls']))
        samples={t:v[:10] for t,v in samples.items()}
        if any(not v for v in samples.values()):
            return jsonify(available=False,reason='Finaliza al menos un partido de cada equipo en este panel para calcular una estimación. No se descargan datos externos.')
        means={t:{k:sum(x[k] for x in v)/len(v) for k in v[0]} for t,v in samples.items()}
        la=max(.05,min(8,(means['a']['gf']+means['b']['ga'])/2))
        lb=max(.05,min(8,(means['b']['gf']+means['a']['ga'])/2))
        probs=[]; win=draw=lose=0
        for a in range(35):
            pa=math.exp(-la)*la**a/math.factorial(a)
            for b in range(35):
                p=pa*math.exp(-lb)*lb**b/math.factorial(b)
                if a>b:win+=p
                elif a==b:draw+=p
                else:lose+=p
                probs.append(dict(home=a,away=b,probability=round(p*100,2)))
        return jsonify(available=True,sample_sizes={t:len(v) for t,v in samples.items()},means=means,
                       expected={'a':round(la,2),'b':round(lb,2)},probabilities={'a':round(win*100,1),'draw':round(draw*100,1),'b':round(lose*100,1)},
                       scorelines=sorted(probs,key=lambda p:-p['probability'])[:3],
                       confidence='Muestra muy pequeña' if min(map(len,samples.values()))<5 else 'Estimación exploratoria',
                       method='Modelo Poisson: promedio entre goles a favor del equipo y goles recibidos por su rival en hasta 10 partidos finalizados registrados aquí. Sin datos externos, sin ajuste por lesiones, localía o calidad de rivales. No está calibrado ni garantiza resultados.')

    @app.post('/api/tournaments/<int:tid>/dates')
    @role('Administrador')
    def dates(tid):
        t=tournament(tid); d=request.get_json()
        start=datetime.fromisoformat(d['start']); gap=number(d.get('gap',7),1,90)
        pending=rows('SELECT * FROM matches WHERE tournament_id=? AND hs IS NULL',(tid,))
        for m in pending:
            date=start+timedelta(days=(m['round']-1)*gap)
            db().execute('UPDATE matches SET date=? WHERE id=?',(date.isoformat(timespec='minutes'),m['id']))
        db().execute('UPDATE tournaments SET start_date=?,gap_days=? WHERE id=?',(d['start'],gap,tid))
        return jsonify(ok=True)

    @app.post('/api/matches/<int:mid>/fixture')
    @role('Administrador')
    def fixture(mid):
        m=one('SELECT * FROM matches WHERE id=?',(mid,)); d=request.get_json()
        if not m or m['hs'] is not None: raise ValueError('Solo se puede programar un partido pendiente.')
        date=str(d.get('date',''))
        if date: datetime.fromisoformat(date)
        db().execute('UPDATE matches SET date=? WHERE id=?',(date,mid))
        return jsonify(ok=True)

    @app.post('/api/tournaments/<int:tid>/leg-plan')
    @role('Administrador','Empleado')
    def leg_plan(tid):
        t=tournament(tid)
        if t['format']=='Liga' or t['sport']=='Baloncesto':raise ValueError('Este formato no tiene eliminatorias de ida y vuelta.')
        if t['champion'] or one('SELECT id FROM matches WHERE tournament_id=? AND hs IS NOT NULL',(tid,)):raise ValueError('El torneo ya comenzó. La modalidad de las llaves se elige antes del primer resultado.')
        count=t['capacity'] if t['format']=='Eliminación directa' else t['groups_count']*t['group_qualifiers'] if t['format']=='Grupos' else t['qualifiers']
        size=2
        while size<count:size*=2
        valid={f'{r}:{slot}' for r in range(1,int(math.log2(size))+1) for slot in range(size//(2**r))}
        plan=request.get_json().get('plan',[])
        if not isinstance(plan,list) or any(not isinstance(x,str) or x not in valid for x in plan):raise ValueError('Selecciona las llaves disponibles en la configuración.')
        db().execute('UPDATE tournaments SET leg_plan=? WHERE id=?',(json.dumps(list(dict.fromkeys(plan))),tid))
        parents=rows("SELECT * FROM matches WHERE tournament_id=? AND phase='Llave' AND return_of IS NULL ORDER BY round,id",(tid,))
        counters={}
        for m in parents:
            slot=m['slot'] if m['slot'] is not None else counters.get(m['round'],0)
            counters[m['round']]=slot+1
            enabled=f"{m['round']}:{slot}" in plan
            child=one('SELECT id FROM matches WHERE return_of=?',(m['id'],))
            if enabled and not child:db().execute("INSERT INTO matches(tournament_id,home,away,round,phase,return_of) VALUES(?,?,?,?,'Llave',?)",(tid,m['away'],m['home'],m['round'],m['id']))
            if not enabled:db().execute('DELETE FROM matches WHERE return_of=?',(m['id'],))
            db().execute('UPDATE matches SET two_legs=?,slot=? WHERE id=?',(int(enabled),slot,m['id']))
        return jsonify(ok=True)

    @app.post('/api/tournaments/<int:tid>/manual-bracket')
    @role('Administrador')
    def manual_bracket(tid):
        t=tournament(tid)
        if t['format']!='Eliminación directa' or one('SELECT id FROM matches WHERE tournament_id=?',(tid,)):
            raise ValueError('Las llaves iniciales se eligen antes de programar una eliminación directa.')
        ts=rows('SELECT * FROM teams WHERE tournament_id=? ORDER BY id',(tid,))
        if len(ts)!=t['capacity']: raise ValueError('Completa todos los equipos.')
        for tm in ts:
            if one('SELECT count(*) n FROM players WHERE team_id=?',(tm['id'],))['n']<SIZES[t['sport']]: raise ValueError('Completa las plantillas antes de crear las llaves.')
        insert_pairs(db,tid,[t['id'] for t in ts],request.get_json()['pairs'],1)
        return jsonify(ok=True)


def insert_pairs(db,tid,eligible,pairs,round_no):
    power=1
    while power<len(eligible):power*=2
    byes=power-len(eligible)
    if not isinstance(pairs,list) or len(pairs)!=power//2: raise ValueError(f'Debes definir {power//2} llaves, incluyendo {byes} pases libres.')
    flat=[]; empty=0
    for pair in pairs:
        if not isinstance(pair,list) or len(pair)!=2: raise ValueError('Cada llave requiere dos posiciones.')
        a,b=pair
        if a is None: raise ValueError('Selecciona el equipo local de cada llave.')
        flat.append(a)
        if b is None:empty+=1
        else:flat.append(b)
    if len(flat)!=len(eligible) or set(flat)!=set(eligible) or empty!=byes:
        raise ValueError('Cada clasificado debe aparecer exactamente una vez y los pases libres deben completar el cuadro.')
    stored=json.loads(db().execute('SELECT bracket_rounds FROM tournaments WHERE id=?',(tid,)).fetchone()['bracket_rounds'])
    stored[str(round_no)]=pairs
    db().execute('UPDATE tournaments SET bracket_rounds=? WHERE id=?',(json.dumps(stored),tid))
    for slot,(a,b) in enumerate(pairs):
        if b is not None:
            plan=json.loads(db().execute('SELECT leg_plan FROM tournaments WHERE id=?',(tid,)).fetchone()['leg_plan'])
            enabled=f'{round_no}:{slot}' in plan
            mid=db().execute("INSERT INTO matches(tournament_id,home,away,round,phase,slot,two_legs) VALUES(?,?,?,?,'Llave',?,?)",(tid,a,b,round_no,slot,int(enabled))).lastrowid
            if enabled:db().execute("INSERT INTO matches(tournament_id,home,away,round,phase,return_of) VALUES(?,?,?,?,'Llave',?)",(tid,b,a,round_no,mid))
