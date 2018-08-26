#!/usr/bin/env python3
# coding: utf-8

from brt import BRT
import json
from collections import namedtuple, defaultdict
import configparser
import sys

VStar=namedtuple('VStar', 'name comm expos')

config = configparser.ConfigParser()
config.read('brt/telescope.ini')

print('Log in to telescope.org ...')

brt=BRT.Telescope(config['telescope.org']['user'],config['telescope.org']['password'])
BRT.astrometryAPIkey=config['astrometry.net']['apikey']

obslst=[
    VStar('SS Cyg', comm='Mira', expos=180),
    VStar('EU Cyg',comm='Mira', expos=180),
    VStar('IP Cyg',comm='Mira', expos=180),
    VStar('V686 Cyg',comm='Mira',expos=180),
    VStar('AS Lac',comm='Mira', expos=120),
    VStar('BI Her',comm='Mira', expos=180),
    VStar('DX Vul',comm='Mira', expos=180),
    VStar('DQ Vul',comm='Mira', expos=180),
    VStar('EQ Lyr',comm='Mira', expos=180),
    VStar('LX Cyg', comm='AAVSO', expos=180)]

print('Getting observing queue ...')

reqlst=brt.get_user_requests(sort='completion')
q=[r for r in reqlst if int(r['status'])<8]
qn=[r['objectname'] for r in q]

print('Submitting missing jobs ...')

if not (len(sys.argv)>1 and sys.argv[1]=='-y' ):
    print('Dry run. Add -y to the command line to do actual submissions.')
    
for vs in [vs for vs in obslst if vs.name not in qn]:
    print(vs)
    if len(sys.argv)>1 and sys.argv[1]=='-y' :
        brt.submitVarStar(vs.name, expos=vs.expos, comm=vs.comm)

print('Done.')
