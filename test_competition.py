import unittest
import json
import test_app


class CompetitionTest(unittest.TestCase):
    setUp=test_app.CanchaTest.setUp
    tearDown=test_app.CanchaTest.tearDown
    post=test_app.CanchaTest.post
    tournament=test_app.CanchaTest.tournament

    def test_fixed_brackets_16_and_32(self):
        for size in (16,32):
            tid,d=self.tournament('Eliminación directa',size)
            self.assertEqual(d['standings'],[])
            slots=json.loads(d['tournament']['bracket_rounds'])['1']
            self.assertEqual(len(slots),size//2)
            self.assertEqual(len(set(x for pair in slots for x in pair)),size)
            for a,b in slots:
                m=next(m for m in d['matches'] if m['home']==a and m['away']==b)
                self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=1,aws=0)).status_code,200)
            self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
            after=self.c.get(f'/api/tournaments/{tid}').json
            second=json.loads(after['tournament']['bracket_rounds'])['2']
            self.assertEqual(second,[[slots[i][0],slots[i+1][0]] for i in range(0,len(slots),2)])

    def test_shootout_requires_takers_and_tie(self):
        tid,d=self.tournament('Eliminación directa',2)
        m=d['matches'][0]
        r=self.post(f"/matches/{m['id']}",dict(hs=1,aws=1,hp=5,ap=3))
        self.assertEqual(r.status_code,400);self.assertIn('cobrador',r.json['error'])
        lineups={str(t['id']):[p['id'] for p in d['players'] if p['team_id']==t['id']][:5] for t in d['teams']}
        events=[]
        for i in range(3):
            events.extend([dict(type='Penal de tanda',player=lineups[str(m['home'])][i],minute=40,second=i*2,outcome='Gol'),dict(type='Penal de tanda',player=lineups[str(m['away'])][i],minute=40,second=i*2+1,outcome='Fallado')])
        payload=dict(hs=1,aws=1,lineups=lineups,events=events)
        self.assertEqual(self.post(f"/matches/{m['id']}",payload).status_code,200)
        saved=self.c.get(f'/api/tournaments/{tid}').json['matches'][0]
        self.assertEqual((saved['hp'],saved['ap'],saved['winner']),(3,0,m['home']))
        self.assertEqual(len(saved['events']),6)
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(payload,hs=2)).status_code,400)

    def test_add_players_after_schedule_keeps_existing(self):
        tid,d=self.tournament()
        team=d['teams'][0]['id'];before=d['players']
        r=self.post(f'/teams/{team}/players',dict(players=[dict(name='Nuevo jugador',number=99,position='portero')]))
        self.assertEqual(r.status_code,200,r.json)
        after=self.c.get(f'/api/tournaments/{tid}').json
        self.assertEqual(len(after['players']),len(before)+1)
        self.assertEqual(after['matches'][0]['id'],d['matches'][0]['id'])
        for p in before:self.assertIn(p,after['players'])

    def test_group_qualifiers_configurable(self):
        for per_group in (1,3):
            r=self.post('/tournaments',dict(name='Copa grupos',sport='Futsal',format='Grupos',capacity=6,groups_count=2,group_qualifiers=per_group,duration=40))
            self.assertEqual(r.status_code,200,r.json);tid=r.json['id']
            for i in range(6):self.post(f'/tournaments/{tid}/teams',dict(name=f'Club {i}'))
            d=self.c.get(f'/api/tournaments/{tid}').json
            for t in d['teams']:
                self.post(f"/teams/{t['id']}/players",dict(players=[dict(name=f'Jugador {j}',number=j,position='Delantero') for j in range(5)]))
            self.post(f'/tournaments/{tid}/schedule',{})
            d=self.c.get(f'/api/tournaments/{tid}').json
            for m in d['matches']:
                self.post(f"/matches/{m['id']}",dict(hs=int(m['home']<m['away']),aws=int(m['home']>m['away'])))
            self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
            after=self.c.get(f'/api/tournaments/{tid}').json
            self.assertEqual(len(json.loads(after['tournament']['qualified_ids'])),per_group*2)
            self.assertTrue(after['tournament']['closed'])




    def test_mixed_two_legs(self):
        tid,d=self.tournament('Eliminación directa',4)
        first,other=d['matches']
        self.assertEqual(self.post(f"/matches/{first['id']}/two-legs",dict(enabled=True)).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        back=next(m for m in d['matches'] if m['return_of']==first['id'])
        self.assertEqual((back['home'],back['away']),(first['away'],first['home']))
        self.assertEqual(self.post(f"/matches/{back['id']}",dict(hs=0,aws=0)).status_code,400)
        self.assertEqual(self.post(f"/matches/{first['id']}",dict(hs=2,aws=0)).status_code,200)
        self.assertEqual(self.post(f"/matches/{other['id']}",dict(hs=1,aws=0)).status_code,200)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,400)
        self.assertEqual(self.post(f"/matches/{back['id']}",dict(hs=1,aws=0)).status_code,200)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json
        final=next(m for m in d['matches'] if m['round']==2)
        self.assertEqual({final['home'],final['away']},{first['home'],other['home']})

    def test_two_legs_draw_and_toggle(self):
        tid,d=self.tournament('Eliminación directa',2);m=d['matches'][0]
        url=f"/matches/{m['id']}/two-legs"
        for enabled in (True,False,True):self.assertEqual(self.post(url,dict(enabled=enabled)).status_code,200)
        d=self.c.get(f'/api/tournaments/{tid}').json;back=next(x for x in d['matches'] if x['return_of'])
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=0,aws=0)).status_code,200)
        self.assertEqual(self.post(url,dict(enabled=False)).status_code,400)
        self.assertEqual(self.post(f"/matches/{back['id']}",dict(hs=1,aws=1)).status_code,400)
        self.assertEqual(self.post(f"/matches/{back['id']}",dict(hs=0,aws=1)).status_code,200)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        self.assertEqual(self.c.get(f'/api/tournaments/{tid}').json['tournament']['champion'],m['home'])

    def test_two_legs_shootout_uses_aggregate(self):
        tid,d=self.tournament('Eliminación directa',2);m=d['matches'][0]
        self.post(f"/matches/{m['id']}/two-legs",dict(enabled=True))
        self.post(f"/matches/{m['id']}",dict(hs=2,aws=0))
        back=next(x for x in self.c.get(f'/api/tournaments/{tid}').json['matches'] if x['return_of'])
        lineups={str(t['id']):[p['id'] for p in d['players'] if p['team_id']==t['id']][:5] for t in d['teams']}
        events=[]
        for i in range(3):
            events.extend([dict(type='Penal de tanda',player=lineups[str(back['home'])][i],minute=40,second=i*2,outcome='Gol'),dict(type='Penal de tanda',player=lineups[str(back['away'])][i],minute=40,second=i*2+1,outcome='Fallado')])
        payload=dict(hs=2,aws=0,lineups=lineups,events=events)
        self.assertEqual(self.post(f"/matches/{back['id']}",payload).status_code,200)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        self.assertEqual(self.c.get(f'/api/tournaments/{tid}').json['tournament']['champion'],back['home'])
    def test_optional_match_statistics(self):
        tid,d=self.tournament('Eliminación directa',2);m=d['matches'][0]
        stats={str(m['home']):dict(possession=58,passes=200,completed_passes=150),str(m['away']):dict(possession=42)}
        r=self.post(f"/matches/{m['id']}",dict(hs=1,aws=0,metrics=stats))
        self.assertEqual(r.status_code,200,r.json)
        saved=self.c.get(f'/api/tournaments/{tid}').json['matches'][0]
        self.assertEqual(saved['metrics'],stats)
        stats[str(m['away'])]['possession']=50
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=1,aws=0,metrics=stats)).status_code,400)
        stats[str(m['away'])]['possession']=42;stats[str(m['home'])]['completed_passes']=201
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=1,aws=0,metrics=stats)).status_code,400)
    def test_leg_plan_locked_after_any_result_and_future_round(self):
        tid,d=self.tournament('Eliminación directa',4)
        r=self.post(f'/tournaments/{tid}/leg-plan',dict(plan=['2:0']))
        self.assertEqual(r.status_code,200,r.json)
        for m in d['matches']:self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=1,aws=0)).status_code,200)
        self.assertEqual(self.post(f'/tournaments/{tid}/leg-plan',dict(plan=[])).status_code,400)
        self.assertEqual(self.post(f'/tournaments/{tid}/advance',{}).status_code,200)
        after=self.c.get(f'/api/tournaments/{tid}').json
        final=next(m for m in after['matches'] if m['round']==2 and not m['return_of'])
        self.assertEqual(final['two_legs'],1)
        self.assertTrue(any(m['return_of']==final['id'] for m in after['matches']))
        self.assertEqual(self.post(f"/matches/{final['id']}/two-legs",dict(enabled=False)).status_code,400)

    def test_independent_passes_and_manual_totals_persist(self):
        tid,d=self.tournament('Eliminación directa',2);m=d['matches'][0]
        metrics={str(m['home']):dict(completed_passes=50,manual_remates=12,manual_corners=6),str(m['away']):dict(completed_passes=45,manual_remates=9)}
        self.assertEqual(self.post(f"/matches/{m['id']}",dict(hs=1,aws=0,metrics=metrics)).status_code,200)
        saved=self.c.get(f'/api/tournaments/{tid}').json['matches'][0]
        self.assertEqual(saved['metrics'],metrics)
