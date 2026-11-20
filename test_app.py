import tempfile
import unittest
from pathlib import Path
from app import create_app


class CanchaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(str(Path(self.tmp.name)/'test.sqlite'))
        self.app.config['TESTING']=True
        self.c=self.app.test_client()
        self.csrf=self.c.get('/api/session').json['csrf']
        self.post('/setup',dict(name='Administrador',email='admin@example.test',password='Test-only-12345'))
        self.post('/login',dict(email='admin@example.test',password='Test-only-12345'))
        self.csrf=self.c.get('/api/session').json['csrf']

    def tearDown(self):
        self.tmp.cleanup()

    def post(self,path,d):
        return self.c.post('/api'+path,json=d,headers={'X-CSRF-Token':self.csrf})

    def tournament(self,fmt='Liga',n=2,sport='Futsal'):
        r=self.post('/tournaments',dict(name='Copa de prueba',sport=sport,format=fmt,capacity=n,duration=40,groups_count=2))
        self.assertEqual(r.status_code,200,r.json)
        tid=r.json['id']
        for i in range(n):self.post(f'/tournaments/{tid}/teams',dict(name=f'Equipo {i}'))
        detail=self.c.get(f'/api/tournaments/{tid}').json
        for t in detail['teams']:
            self.post(f"/teams/{t['id']}/players",dict(players=[dict(name=f'Jugador {i}',number=i,position='Base' if sport=='Baloncesto' else 'Delantero') for i in range(6)]))
        r=self.post(f'/tournaments/{tid}/schedule',{})
        self.assertEqual(r.status_code,200,r.json)
        return tid,self.c.get(f'/api/tournaments/{tid}').json

    def test_security(self):
        self.assertEqual(self.c.post('/api/tournaments',json={}).status_code,403)
        self.post('/users',dict(name='Empleado',email='emp@example.test',password='Test-only-12345',role='Empleado'))
        self.post('/logout',{})
        self.csrf=self.c.get('/api/session').json['csrf']
        self.post('/login',dict(email='emp@example.test',password='Test-only-12345'))
        self.csrf=self.c.get('/api/session').json['csrf']
        self.assertEqual(self.post('/tournaments',{}).status_code,403)
        self.assertEqual(self.c.get('/api/users').status_code,403)

    def test_league_round_robin_and_corrections(self):
        tid,d=self.tournament(n=5)
        self.assertEqual(len(d['matches']),10)
        self.assertEqual(len({tuple(sorted((m['home'],m['away']))) for m in d['matches']}),10)
        self.assertEqual(self.post(f'/tournaments/{tid}/schedule',{}).status_code,400)
        m=d['matches'][0]
        for _ in range(2):self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=2,aws=1)).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        r=next(x for x in d['standings'] if x['id']==m['home'])
        self.assertEqual((r['pj'],r['pts'],r['gf']),(1,3,2))

    def test_bracket_byes_and_champion(self):
        tid,d=self.tournament('Eliminación directa',5)
        self.assertEqual(len(d['matches']),1)
        for _ in range(3):
            d=self.c.get(f'/api/tournaments/{tid}').json
            for m in d['matches']:
                if m['hs'] is None:self.post(f"/matches/{m['id']}",dict(hs=1,aws=0))
            self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        self.assertIsNotNone(d['tournament']['champion'])
        self.assertEqual(self.post(f"/matches/{d['matches'][0]['id']}",dict(hs=0,aws=1)).status_code,400)

    def test_group_stage(self):
        tid,d=self.tournament('Grupos',4)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,400)
        for m in d['matches']:self.post(f"/matches/{m['id']}",dict(hs=0,aws=0))
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,400)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',dict(order=[t['id'] for t in d['teams']])).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        self.assertEqual(len([m for m in d['matches'] if m['phase']=='Llave']),2)

    def test_events_and_expulsion(self):
        tid,d=self.tournament()
        m=d['matches'][0]
        lineups={str(t['id']):[p['id'] for p in d['players'] if p['team_id']==t['id']][:5] for t in d['teams']}
        p=lineups[str(m['home'])][0]
        events=[dict(minute=1,type='Gol',player=p),dict(minute=2,type='Roja',player=p)]
        r=self.post(f"/matches/{m['id']}",dict(hs=1,aws=0,lineups=lineups,events=events))
        self.assertEqual(r.status_code,200,r.json)
        events.append(dict(minute=3,type='Gol',player=p))
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=2,aws=0,lineups=lineups,events=events)).status_code,400)
        d=self.c.get(f'/api/tournaments/{tid}').json
        self.assertEqual(next(x for x in d['statistics'] if x['id']==p)['goals'],1)

    def test_duplicate_dorsal_atomic(self):
        tid=self.post('/tournaments',dict(name='Copa test',sport='Futsal',format='Liga',capacity=2,duration=40)).json['id']
        self.post(f'/tournaments/{tid}/teams',dict(name='Equipo uno'))
        team=self.c.get(f'/api/tournaments/{tid}').json['teams'][0]['id']
        r=self.post(f'/teams/{team}/players',dict(players=[dict(name='Uno',number=1,position='Portero'),dict(name='Dos',number=1,position='Defensa')]))
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.c.get(f'/api/tournaments/{tid}').json['players'],[])

    def test_basketball_tie(self):
        tid,d=self.tournament(sport='Baloncesto')
        self.assertEqual(self.post(f"/matches/{d['matches'][0]['id']}",dict(hs=50,aws=50)).status_code,400)

    def test_lockout(self):
        self.post('/logout',{})
        self.csrf=self.c.get('/api/session').json['csrf']
        for _ in range(5):self.assertEqual(self.post('/login',dict(email='admin@example.test',password='wrong')).status_code,401)
        self.assertEqual(self.post('/login',dict(email='admin@example.test',password='Test-only-12345')).status_code,429)


if __name__=='__main__':unittest.main()
