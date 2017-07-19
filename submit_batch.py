#!/usr/bin/env python

from __future__ import print_function, division, absolute_import

import time
import configparser
import BRT
from requests import session
from bs4 import BeautifulSoup
from io import StringIO, BytesIO
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy import wcs
import astropy.units as u
from pyvo import conesearch
import sys

config = configparser.ConfigParser()
config.read('telescope.ini')

brt=BRT.Telescope(config['telescope.org']['user'],config['telescope.org']['password'])
BRT.astrometryAPIkey=config['astrometry.net']['apikey']


def submitVS(t):
    #t.submitVarStar('QZ Vir',comm='Cataclismic')
    #t.submitVarStar('RS Leo',comm='Unkn', expos=80)

    t.submitVarStar('SS Cyg',comm='Mira', expos=180)
    t.submitVarStar('EU Cyg',comm='Mira', expos=180)
    t.submitVarStar('IP Cyg',comm='Mira', expos=240)
    t.submitVarStar('V686 Cyg',comm='Mira',expos=240)
    t.submitVarStar('AS Lac',comm='Mira', expos=120)
    t.submitVarStar('BI Her',comm='Mira', expos=240)
    t.submitVarStar('DX Vul',comm='Mira', expos=240)
    t.submitVarStar('DQ Vul',comm='Mira', expos=180)
    t.submitVarStar('EQ Lyr',comm='Mira', expos=240)
    t.submitVarStar('AG Dra',comm='AAVSO', expos=30)


if len(sys.argv)>1 :
    ex=90
    comment=""
    if len(sys.argv)>2 :
        ex=int(sys.argv[2])
    if len(sys.argv)>3 :
        comment=sys.argv[3]
    brt.submitVarStar(sys.argv[1],expos=ex,comm=comment)
else :
    submitVS(brt)

