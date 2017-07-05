#!/usr/bin/env python

from __future__ import print_function, division, absolute_import

import time
import os
import configparser
import BRT
from requests import session
from bs4 import BeautifulSoup
from zipfile import ZipFile
from io import StringIO, BytesIO
from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy import wcs
import astropy.units as u
from pyvo import conesearch
import sys
from pylab import *

config = configparser.ConfigParser()
config.read('telescope.ini')

brt=BRT.Telescope(config['telescope.org']['user'],config['telescope.org']['password'])
BRT.astrometryAPIkey=config['astrometry.net']['apikey']


def submitVS(t):
    #t.submitVarStar('QZ Vir',comm='Cataclismic')
    #t.submitVarStar('RS Leo',comm='Unkn', expos=80)
    t.submitVarStar('SS Cyg',comm='Mira')
    t.submitVarStar('EU Cyg',comm='Mira')
    t.submitVarStar('IP Cyg',comm='Mira', expos=180)
    t.submitVarStar('V686 Cyg',comm='Mira')
    t.submitVarStar('AS Lac',comm='Mira')
    t.submitVarStar('BI Her',comm='Mira')
    t.submitVarStar('DX Vul',comm='Mira')
    t.submitVarStar('EQ Lyr',comm='Mira')

submitVS(brt)

