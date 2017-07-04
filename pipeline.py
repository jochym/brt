#!/bin/env python3

from __future__ import print_function, division

import time
import os
import configparser
from brt import BRT
from requests import session
from bs4 import BeautifulSoup
from zipfile import ZipFile
from io import StringIO, BytesIO
from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy import wcs
import astropy.units as u
from pyvo import conesearch

config = configparser.ConfigParser()
config.read('telescope.ini')

def searchVS(h, cat='GCVS', caturl=None, maxSearchRadius=5):
    '''
    Search the area of the image in h (hdu, fits) for variable stars
    using the given catalogue. The cat imput parameter denotes the 
    catalogue:
    
    'GCVS' - use the General Catalogue of Variable Stars
    'VSX'  - use the AAVSO Variable Star Index
    'USER' - use the custom url passed in caturl parameter
    
    The maximum search radius is specified by maxSearchRadius (deg).
    
    Returns a list of VS in the circle with the frame inscribed in it.
    '''
    
    if cat=='GCVS' :
        caturl='http://vizier.u-strasbg.fr/viz-bin/votable/-A?-source=B/vsx&amp;'
    elif cat=='VSX' :
        caturl='http://heasarc.gsfc.nasa.gov/cgi-bin/vo/cone/coneGet.pl?table=aavsovsx&amp;'
    else :
        caturl=caturl
    
    w=wcs.WCS(h[0].header)
    cen=w.all_pix2world(array([[h[0].header['NAXIS1'], h[0].header['NAXIS2']]])/2,0)[0]
    # Half of the hypotenuse of the frame = radius of the search
    rad=sqrt(sum((real(eigvals(w.wcs.cd))*array([h[0].header['NAXIS1'], h[0].header['NAXIS2']]))**2))/2
    # Clamp to reasonable size
    rad=min(rad, maxSearchRadius)
    r=conesearch(caturl,pos=list(cen),radius=rad)
    return r

