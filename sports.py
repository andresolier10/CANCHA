"""Reglas compartidas por las actas y el panel independiente en vivo."""
from collections import defaultdict
import unicodedata


def normalize_position(value, allowed):
    def key(text):
        return ''.join(c for c in unicodedata.normalize('NFD', str(text).strip().casefold()) if not unicodedata.combining(c)).replace(' ', '').replace('-', '')
    positions={key(p):p for p in allowed}
    result=positions.get(key(value)) if value is not None else None
    if result is None:
        raise ValueError('Posición "'+str(value or '')+'" no válida. Usa: '+', '.join(sorted(allowed))+'.')
    return result

SIZES = {'Fútbol 11': 11, 'Fútbol 7': 7, 'Futsal': 5, 'Baloncesto': 5}
FOOTBALL_EVENTS = ['Gol', 'Remate', 'Penal', 'Penal fallado', 'Autogol', 'Asistencia', 'Falta', 'Entrada', 'Ocasión clara fallada', 'Córner', 'Fuera de juego', 'Parada', 'Amarilla', 'Roja', 'Sustitución', 'Penal de tanda']
BASKET_EVENTS = ['Punto', 'Remate', 'Asistencia', 'Falta', 'Rebote', 'Robo', 'Pérdida', 'Sustitución']


def number(value, low=0, high=999):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError('Se requiere un número entero válido.')
    if isinstance(value, bool) or str(value).strip() != str(result) or not low <= result <= high:
        raise ValueError(f'Ingresa un entero entre {low} y {high}.')
    return result


def analyze(sport, duration, team_ids, players, squads, lineups, events, require_lineups=False):
    """Reproduce los eventos en orden y obtiene marcador, elegibilidad y estadísticas."""
    team_ids = [str(t) for t in team_ids]
    roster = {number(p['id'], 1, 10**9): dict(p, team_id=str(p['team_id'])) for p in players}
    active, removed, expelled = set(), set(), set()
    yellows, fouls = defaultdict(int), defaultdict(int)
    stats = {t: dict(goals=0, points=0, shots=0, on_target=0, fouls=0, tackles=0,
                    big_misses=0, yellows=0, reds=0, assists=0, penalties=0, penalties_scored=0,
                    shootout_scored=0, shootout_taken=0, rebounds=0, steals=0, turnovers=0,
                    corners=0, offsides=0, saves=0, own_goals=0, substitutions=0) for t in team_ids}
    individual = {p: dict(roster[p], **{k: 0 for k in next(iter(stats.values()))}) for p in roster}
    called = set()
    must = bool(events or lineups or require_lineups)
    if not isinstance(events, list) or len(events) > 2000:
        raise ValueError('El acta admite hasta 2000 eventos.')
    for tid in team_ids:
        squad = squads.get(tid, [])
        starting = lineups.get(tid, [])
        if len(squad) != len(set(squad)) or any(p not in roster or roster[p]['team_id'] != tid for p in squad):
            raise ValueError('La convocatoria contiene jugadores repetidos o ajenos al equipo.')
        called.update(squad)
        if must and (len(starting) != SIZES[sport] or len(set(starting)) != len(starting)):
            raise ValueError(f'Selecciona exactamente {SIZES[sport]} titulares por equipo.')
        if any(p not in squad for p in starting):
            raise ValueError('Todos los titulares deben estar convocados.')
        active.update(starting)
    last = -1
    shootout_started = False
    last_shootout_team = None
    shootout_used = {t: set() for t in team_ids}
    normalized = []
    for source in events:
        e = dict(source)
        minute = number(e.get('minute'), 0, duration + 180)
        second = number(e.get('second', 0), 0, 59)
        when = minute * 60 + second
        if when < last:
            raise ValueError('Ordena los eventos cronológicamente (minuto y segundo).')
        last = when
        pid = number(e.get('player'), 1, 10**9)
        kind = e.get('type')
        if kind not in (BASKET_EVENTS if sport == 'Baloncesto' else FOOTBALL_EVENTS):
            raise ValueError('Evento no válido para este deporte.')
        if pid not in active or pid in expelled:
            raise ValueError(f"Minuto {minute}:{second:02d} · {kind}: {roster.get(pid, {}).get('name', 'el jugador')} no está en cancha o fue expulsado. Selecciona un jugador que esté jugando en ese momento.")
        tid = roster[pid]['team_id']
        other = next(t for t in team_ids if t != tid)
        e.update(player=pid, minute=minute, second=second, team_id=tid,
                 note=str(e.get('note', ''))[:300])
        def add(key, amount=1, target=tid):
            stats[target][key] += amount
            if target == tid:
                individual[pid][key] += amount
        if shootout_started and kind != 'Penal de tanda':
            raise ValueError('Después de iniciar la tanda solo se admiten penales de tanda.')
        if kind == 'Sustitución':
            incoming = number(e.get('incoming'), 1, 10**9)
            if incoming not in called or roster[incoming]['team_id'] != tid or incoming in active or incoming in expelled:
                raise ValueError(f'Minuto {minute}:{second:02d} · Sustitución: el jugador que entra debe ser un suplente de este equipo. Márcalo como Convocado (disponible para este partido), sin marcarlo Titular; no puede estar jugando ni expulsado.')
            if sport in ('Fútbol 11', 'Fútbol 7') and incoming in removed:
                raise ValueError('No se permite el reingreso en esta modalidad.')
            active.remove(pid); removed.add(pid); active.add(incoming)
            add('substitutions')
            e['incoming'] = incoming
        elif kind in ('Gol', 'Penal', 'Punto', 'Autogol'):
            if kind == 'Punto':
                e['value'] = number(e.get('value', 1), 1, 3)
                add('points', e['value']); add('shots'); add('on_target')
            else:
                add('goals', target=other if kind == 'Autogol' else tid)
                if kind == 'Autogol': add('own_goals')
                if kind != 'Autogol': add('shots'); add('on_target')
                if kind == 'Penal': add('penalties'); add('penalties_scored')
        elif kind == 'Remate':
            if e.get('outcome') not in ('Al arco', 'Fuera', 'Bloqueado'):
                raise ValueError('Indica si el remate fue al arco, fuera o bloqueado.')
            add('shots')
            if e['outcome'] == 'Al arco': add('on_target')
        elif kind == 'Penal fallado':
            if e.get('outcome') not in ('Al arco', 'Fuera', 'Bloqueado'):
                raise ValueError('Indica cómo terminó el penal fallado.')
            add('penalties'); add('shots')
            if e['outcome'] == 'Al arco': add('on_target')
        elif kind == 'Ocasión clara fallada':
            add('big_misses'); add('shots')
            if e.get('outcome') == 'Al arco': add('on_target')
        elif kind == 'Amarilla':
            add('yellows'); yellows[pid] += 1
            if yellows[pid] == 2:
                add('reds'); expelled.add(pid); active.remove(pid)
        elif kind == 'Roja':
            add('reds'); expelled.add(pid); active.remove(pid)
        elif kind == 'Falta':
            add('fouls'); fouls[pid] += 1
            if sport == 'Baloncesto' and fouls[pid] >= 5:
                expelled.add(pid); active.remove(pid)
        elif kind == 'Penal de tanda':
            if shootout_winner(stats,team_ids):
                raise ValueError('La tanda ya tiene un ganador; no se admiten más cobros.')
            if e.get('outcome') not in ('Gol', 'Fallado'):
                raise ValueError('Indica Gol o Fallado en el penal de tanda.')
            if tid == last_shootout_team:
                raise ValueError('Los equipos deben alternarse en la tanda.')
            eligible = {p for p in active if roster[p]['team_id'] == tid}
            if pid in shootout_used[tid] and not eligible.issubset(shootout_used[tid]):
                raise ValueError('Todos los jugadores habilitados deben cobrar antes de repetir cobrador.')
            if eligible.issubset(shootout_used[tid]): shootout_used[tid].clear()
            shootout_used[tid].add(pid)
            shootout_started = True; last_shootout_team = tid
            add('shootout_taken')
            if e['outcome'] == 'Gol': add('shootout_scored')
        else:
            key = {'Entrada': 'tackles', 'Asistencia': 'assists', 'Rebote': 'rebounds', 'Robo': 'steals', 'Pérdida': 'turnovers', 'Córner':'corners', 'Fuera de juego':'offsides', 'Parada':'saves'}[kind]
            add(key)
        if kind not in ('Remate','Penal fallado','Ocasión clara fallada','Penal de tanda'):e.pop('outcome',None)
        normalized.append(e)
    return dict(events=normalized, teams=stats, players=list(individual.values()),
                active=sorted(active), expelled=sorted(expelled), called=sorted(called))


def shootout_winner(teams, ids):
    a, b = [teams[str(t)] for t in ids]
    sa, sb = a['shootout_scored'], b['shootout_scored']
    na, nb = a['shootout_taken'], b['shootout_taken']
    if na <= 5 and nb <= 5:
        if sa > sb + (5 - nb): return str(ids[0])
        if sb > sa + (5 - na): return str(ids[1])
    if na == nb and na >= 5 and sa != sb:
        return str(ids[0] if sa > sb else ids[1])
    return None
