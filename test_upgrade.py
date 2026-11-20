import json
import unittest
import test_app
from sports import analyze


class UpgradeTest(unittest.TestCase):
    setUp=test_app.CanchaTest.setUp
    tearDown=test_app.CanchaTest.tearDown
    post=test_app.CanchaTest.post
    tournament=test_app.CanchaTest.tournament
    def create_series(self, sport='Futsal'):
        r=self.post('/live',dict(home='Club Azul',away='Club Verde',sport=sport,duration=40,legs=2,dates=['2026-12-01T18:00','2026-12-08T18:00']))
        self.assertEqual(r.status_code,200,r.json)
        sid=r.json['id']
        def action(action,leg=0,**kwargs):
            rev=self.c.get(f'/api/live/{sid}').json['revision']
            return self.post(f'/live/{sid}/action',dict(action=action,revision=rev,leg=leg,**kwargs))
        players=[dict(team_id=t,name=f'{t} Jugador {n}',number=n,position='Delantero') for t in ('a','b') for n in range(1,7)]
        self.assertEqual(action('roster',players=players).status_code,200)
        for leg in (0,1):
            self.assertEqual(action('lineup',leg=leg,squads={'a':[1,2,3,4,5,6],'b':[7,8,9,10,11,12]},lineups={'a':[1,2,3,4,5],'b':[7,8,9,10,11]}).status_code,200)
        return sid,action

    def test_live_roundtrip_predictions_and_revision(self):
        sid,act=self.create_series()
        self.assertEqual(self.c.get(f'/api/live/{sid}/prediction').json['available'],False)
        self.assertEqual(act('status',leg=1,status='En vivo').status_code,400)
        self.assertEqual(act('status',status='En vivo').status_code,200)
        self.assertEqual(act('event',event=dict(type='Gol',player=1,minute=1)).status_code,200)
        self.assertEqual(act('event',event=dict(type='Remate',player=2,minute=2,outcome='Fuera')).status_code,200)
        d=self.c.get(f'/api/live/{sid}').json
        self.assertEqual(d['legs'][0]['analysis']['teams']['a']['shots'],2)
        self.assertEqual(self.post(f'/live/{sid}/action',dict(action='event',revision=0,leg=0,event={})).status_code,409)
        self.assertEqual(act('status',status='Pausado').status_code,200)
        self.assertEqual(act('clock',seconds=60).status_code,400)
        self.assertEqual(act('clock',seconds=120).status_code,200)
        self.assertEqual(act('status',status='Finalizado').status_code,200)
        p=self.c.get(f'/api/live/{sid}/prediction').json
        self.assertTrue(p['available']);self.assertEqual(p['sample_sizes'],{'a':1,'b':1})
        self.assertAlmostEqual(sum(p['probabilities'].values()),100,delta=.2)
        self.assertEqual(act('status',leg=1,status='En vivo').status_code,200)
        self.assertEqual(act('event',leg=1,event=dict(type='Gol',player=7,minute=2)).status_code,200)
        self.assertEqual(act('status',leg=1,status='Finalizado').status_code,200)
        self.assertIsNone(self.c.get(f'/api/live/{sid}').json['winner'])

    def test_live_convened_and_events(self):
        sid,act=self.create_series()
        bad={'a':[1,2,3,4,5],'b':[7,8,9,10]}
        self.assertEqual(act('lineup',squads=bad,lineups={'a':[1,2,3,4,5],'b':[7,8,9,10,11]}).status_code,400)
        act('status',status='En vivo')
        self.assertEqual(act('event',event=dict(type='Gol',player=6,minute=1)).status_code,400)
        self.assertEqual(act('event',event=dict(type='Sustitución',player=1,incoming=6,minute=1)).status_code,200)
        self.assertEqual(act('event',event=dict(type='Gol',player=6,minute=2)).status_code,200)
        self.assertEqual(act('undo',reason='Gol anulado').status_code,200)
        d=self.c.get(f'/api/live/{sid}').json
        self.assertEqual(d['legs'][0]['analysis']['teams']['a']['goals'],0)
        self.assertEqual(len(d['audit']),1)
        self.assertEqual(act('event',event=dict(type='Amarilla',player=6,minute=2)).status_code,200)
        self.assertEqual(act('event',event=dict(type='Amarilla',player=6,minute=3)).status_code,200)
        d=self.c.get(f'/api/live/{sid}').json
        self.assertEqual(d['legs'][0]['analysis']['teams']['a']['reds'],1)
        self.assertEqual(act('event',event=dict(type='Remate',player=6,minute=4,outcome='Fuera')).status_code,400)

    def test_league_then_elimination_and_dates(self):
        r=self.post('/tournaments',dict(name='Liga y copa',sport='Futsal',format='Fase liguera + eliminatorias',capacity=3,duration=40,legs=2,qualifiers=3,start_date='2026-12-01T17:00',gap_days=7))
        tid=r.json['id']
        for n in range(3):self.post(f'/tournaments/{tid}/teams',dict(name=f'Club {n}'))
        d=self.c.get(f'/api/tournaments/{tid}').json
        for t in d['teams']:self.post(f"/teams/{t['id']}/players",dict(players=[dict(name=f'Jugador {n}',number=n,position='Delantero') for n in range(5)]))
        self.assertEqual(self.post(f'/tournaments/{tid}/schedule',{}).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        self.assertEqual(len(d['matches']),6)
        self.assertTrue(all(m['date'] for m in d['matches']))
        for m in d['matches']:self.post(f"/matches/{m['id']}",dict(hs=1 if m['home']<m['away'] else 0,aws=0 if m['home']<m['away'] else 1))
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        for _ in range(2):
            d=self.c.get(f'/api/tournaments/{tid}').json
            for m in d['matches']:
                if m['hs'] is None:self.post(f"/matches/{m['id']}",dict(hs=1,aws=0))
            self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        self.assertIsNotNone(self.c.get(f'/api/tournaments/{tid}').json['tournament']['champion'])

    def test_league_champion(self):
        tid,d=self.tournament()
        m=d['matches'][0]
        self.post(f"/matches/{m['id']}",dict(hs=3,aws=1))
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        self.assertEqual(self.c.get(f'/api/tournaments/{tid}').json['tournament']['champion'],m['home'])

    def test_manual_crosses(self):
        tid,d=self.tournament('Eliminación directa',4)
        # Elegir la siguiente ronda: no puede incluir equipos eliminados.
        for m in d['matches']:self.post(f"/matches/{m['id']}",dict(hs=1,aws=0))
        winners=[m['home'] for m in d['matches']]
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',dict(pairs=[[winners[0],winners[0]]])).status_code,400)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',dict(pairs=[list(reversed(winners))])).status_code,200)
        final=self.c.get(f'/api/tournaments/{tid}').json['matches'][-1]
        self.assertEqual((final['home'],final['away']),tuple(reversed(winners)))

    def test_shots_authors_and_penalties(self):
        sid,act=self.create_series();act('status',status='En vivo')
        for n in range(10):
            r=act('event',event=dict(type='Remate',player=1 if n<6 else 2,minute=n,outcome='Al arco'))
            self.assertEqual(r.status_code,200,r.json)
        act('event',event=dict(type='Penal fallado',player=3,minute=10,outcome='Fuera'))
        d=self.c.get(f'/api/live/{sid}').json['legs'][0]['analysis']
        self.assertEqual(d['teams']['a']['shots'],11)
        self.assertEqual(next(p for p in d['players'] if p['id']==1)['shots'],6)
        self.assertEqual(next(p for p in d['players'] if p['id']==2)['shots'],4)
        self.assertEqual(next(p for p in d['players'] if p['id']==3)['penalties'],1)

    def test_no_reentry_football(self):
        ps=[dict(id=i,team_id=1 if i<=8 else 2,name=f'J {i}',number=i,position='Defensa') for i in range(1,17)]
        squads={'1':list(range(1,9)),'2':list(range(9,17))};lineups={'1':list(range(1,8)),'2':list(range(9,16))}
        es=[dict(type='Sustitución',player=1,incoming=8,minute=1),dict(type='Sustitución',player=8,incoming=1,minute=2)]
        with self.assertRaisesRegex(ValueError,'reingreso'):analyze('Fútbol 7',60,[1,2],ps,squads,lineups,es)


if __name__=='__main__':unittest.main()
