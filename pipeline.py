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
import diskcache

config = configparser.ConfigParser()
config.read('telescope.ini')

brt=BRT.Telescope(config['telescope.org']['user'],
                    config['telescope.org']['password'],
                    config['cache']['jobs'])
BRT.astrometryAPIkey=config['astrometry.net']['apikey']

wcscache=diskcache.Cache(config['cache']['wcs'])

def get_obs_hdul(brt, jid=None, obs=None):
    '''
    Get list of hdu's in the observation.
    '''
    if obs is not None :
        o=obs
    elif jid is not None :
        o=brt.get_job(jid)
    else :
        return None
    z=brt.get_obs(o,cube=False)
    return [fits.open(BytesIO(z.read(name)))[0] for name in z.namelist()]


def get_obs_shdul(brt, jid=None, obs=None):
    if obs is not None :
        o=obs
    elif jid is not None :
        o=brt.get_job(jid)
    else :
        return None
    hdul=get_obs_hdul(brt, obs=o)
    jid=o['jid']
    filt=o['filter']
    if filt == 'Colour':
        filt='R,G,B'
    elif filt == 'BVR':
        filt='R,V,B'
    elif filt== 'SHO':
        filt = 'SII,Halpha,OIII'
    for h,f in zip(hdul,filt.split(',')):
        h.header['FILTER']=f
        if 'EPOCH' in h.header and h.header['EPOCH'].startswith('REAL'):
            h.header['EPOCH']=2000.0
            h.header['EQUINOX']=2000.0
    shdul=[]
    for h in hdul:
        sjid='_'.join([str(jid), h.header['FILTER']])
        try :
            shdul.append(wcscache[sjid])
        except KeyError :
            h=BRT.solveField(h,name=str(jid),local=True)
            if h :
                wcscache[sjid]=h[0]
                shdul.append(h[0])
    return shdul
    shdul=[BRT.solveField(h,name=str(jid),local=True) for h in hdul]
    shdul=[h[0] for h in shdul if h]
    return shdul


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
    
    w=wcs.WCS(h.header, fix=False)
    cen=w.all_pix2world(array([[h.header['NAXIS1'], h.header['NAXIS2']]])/2,0)[0]
    # Half of the hypotenuse of the frame = radius of the search
    rad=sqrt(sum((real(eigvals(w.wcs.cd))*array([h.header['NAXIS1'], h.header['NAXIS2']]))**2))/2
    # Clamp to reasonable size
    rad=min(rad, maxSearchRadius)
    r=conesearch(caturl,pos=list(cen),radius=rad)
    return r

def analyseJob_old(jid, cat='GCVS'):
    obs=brt.get_job(jid)
    if obs['type']!='SSBODY' :
        print(jid, obs['filter'], obs['exp'], obs['type'], obs['oid'])
        
        z=brt.get_obs(obs,cube=False)
        
        hdul=[fits.open(BytesIO(z.read(name))) for name in z.namelist()]

        for h,f in zip(hdul,obs['filter']):
            h[0].header['FILTER']=f

        shdul=[BRT.solveField(h[0],name=str(jid)) for h in hdul]
        for n,h in enumerate(shdul):
            print('Filter: ',hdul[n][0].header['FILTER'],end=' ')
            if h is None :
                print('Unable to solve the field!')
                imshow(sqrt(hdul[n][0].data),aspect='equal')
                continue
            w=wcs.WCS(h[0].header)
            imshow(sqrt(h[0].data),aspect='equal')
            plot(h[0].header['NAXIS1']/2,h[0].header['NAXIS2']/2,'r+',ms=30)
            if obs['type']=='RADEC':
                obj=SkyCoord(obs['oid'], unit=(u.hourangle, u.deg))
            else :
                obj=SkyCoord.from_name(obs['type']+obs['oid'])
            pix=w.all_world2pix(array([[obj.ra.deg,obj.dec.deg]]),0)[0]
            plot(pix[0],pix[1],'r+',ms=20)
            plot(pix[0],pix[1],'ro',fillstyle='none', ms=12)
            r=searchVS(h)
            print("Number of VS:", len(r))
            for rec in r:
                s={k:rec[k] for k in rec.keys()}
                s['Name'] = s['Name'].decode('ascii')
                vsname='%(Name)-25s' % s
                # filter out NSV and VSX hits (leave just GCVS marked stars)
                if vsname.find('NSV')<0 and vsname.find('VSX')<0 :
                    pix=w.all_world2pix(array([[rec.ra,rec.dec]]),0)[0]
                    # reject out of frame stars
                    if 0 < pix[0] < h[0].header['NAXIS1'] and 0 < pix[1] < h[0].header['NAXIS2'] :
                        plot(pix[0],pix[1],'ro',fillstyle='none')
                        annotate(vsname, pix, xytext=(5,-7), textcoords='offset points', color='y')
                        print('%(Name)25s %(Period)12.6f %(min)6.2f - %(max)6.2f ' % s)
            xlim(0,h[0].header['NAXIS1'])
            ylim(0,h[0].header['NAXIS2'])
            show()
        print()

def analyse_job(obs, cat='GCVS', local=True):
    blocked_names=['OGLE', 'MACHO', 'NSV', 'VSX', 'CSS', 'SWASP', 'CAG', 'ASAS', 'SDSS', 'HAT']
#    blocked_names=[]
    try:
        jid=obs['jid']
    except TypeError :
        jid=obs
        obs=brt.get_job(jid)
    
    if obs['type']!='SSBODY' :
        print(jid, obs['filter'], obs['exp'], obs['type'], obs['oid'], end='')
        sys.stdout.flush()
        shdul=get_obs_shdul(brt, obs=obs)
        if shdul :
            print('  Scope:', shdul[0].header['TELESCOP'].strip(), end='')
        vsl=[]
        print(' Filters: ', end='')
        for n,h in enumerate(shdul):
            print(h.header['FILTER'],end=',')
            sys.stdout.flush()
            w=wcs.WCS(h.header)
            if obs['type']=='RADEC':
                obj=SkyCoord(obs['oid'], unit=(u.hourangle, u.deg))
            else :
                obj=SkyCoord.from_name(obs['type']+obs['oid'])
            pix=array(obj.to_pixel(w))
            r=searchVS(h)
            vsl.append([h,[]])
            #print("  Number of VS (unfiltered):", len(r))
            for s in r:
                vsname='%-25s' % s['Name'].decode('ASCII')
                if not any([n in vsname for n in blocked_names]):
                    pix=array(s.pos.to_pixel(w))
                    # reject out of frame stars
                    if 0 < pix[0] < h.header['NAXIS1'] and 0 < pix[1] < h.header['NAXIS2'] :
                        #print('    %-30s' % vsname, '%(Period)12.6f %(min)6.2f - %(max)6.2f ' % s)
                        vsl[n][1].append([vsname, s])
        print()
    return vsl
 
 

def plot_job(jid, cat='GCVS', local=True):
    blocked_names=['OGLE', 'MACHO', 'NSV', 'VSX', 'CSS', 'SWASP', 'CAG', 'ASAS', 'SDSS', 'HAT']
    obs=brt.get_job(jid)
    if obs['type']!='SSBODY' :
        print(jid, obs['filter'], obs['exp'], obs['type'], obs['oid'])
        
        shdul=get_obs_shdul(brt, jid=jid, obs=obs)
        for n,h in enumerate(shdul):
            if h is None :
                print('Unable to solve the field!')
                continue
            print('   Scope: ', h.header['TELESCOP'], 'Filter: ',h.header['FILTER'],end='')
            w=wcs.WCS(h.header)
            imshow((h.data-h.data.min())**(1/3),aspect='equal')
            plot(h.header['NAXIS1']/2,h.header['NAXIS2']/2,'r+',ms=30)
            if obs['type']=='RADEC':
                obj=SkyCoord(obs['oid'], unit=(u.hourangle, u.deg))
            else :
                obj=SkyCoord.from_name(obs['type']+obs['oid'])
            pix=array(obj.to_pixel(w))
            plot(pix[0],pix[1],'r+',ms=20)
            plot(pix[0],pix[1],'ro',fillstyle='none', ms=12)
            r=searchVS(h)
            print("  Number of VS (unfiltered):", len(r))
            for s in r:
                vsname='%-25s' % s['Name'].decode('ASCII')
                # filter out NSV and VSX hits (leave just GCVS marked stars)
                if not any([n in vsname for n in blocked_names]):
                #if vsname.find('NSV')<0 and vsname.find('VSX')<0 :
                    pix=array(s.pos.to_pixel(w))
                    # reject out of frame stars
                    if 0 < pix[0] < h.header['NAXIS1'] and 0 < pix[1] < h.header['NAXIS2'] :
                        plot(pix[0],pix[1],'ro',fillstyle='none')
                        annotate(vsname, pix, xytext=(5,-7), textcoords='offset points', color='y')
                        print('%25s' % vsname, '%(Period)12.6f %(min)6.2f - %(max)6.2f ' % s)
            xlim(0,h.header['NAXIS1'])
            ylim(0,h.header['NAXIS2'])
            show()
        print()
    

def plot_frame(h, vsl=None):
    print('  Scope: ', h.header['TELESCOP'], 'Filter: ',h.header['FILTER'])
    w=wcs.WCS(h.header)
    imshow((h.data-h.data.min())**(1/3),aspect='equal')
    plot(h.header['NAXIS1']/2,h.header['NAXIS2']/2,'r+',ms=30)
    for vsname, s in vsl:
        pix=array(s.pos.to_pixel(w))
        # reject out of frame stars
        if 0 < pix[0] < h.header['NAXIS1'] and 0 < pix[1] < h.header['NAXIS2'] :
            plot(pix[0],pix[1],'ro',fillstyle='none')
            annotate(vsname, pix, xytext=(5,-7), textcoords='offset points', color='y')
    xlim(0,h.header['NAXIS1'])
    ylim(0,h.header['NAXIS2'])
    show()


def get_VS_sequence(vs):
    pass

BRT.DEBUG=1
#jid=293657
#vlst=analyse_job(jid)
#plot_job(jid)

import re

vsre = re.compile('([V][0-9]+)|([R-Z])|([R-Z][R-Z])|([A-IK-Q][A-IK-Z])')

if len(sys.argv)>1 :
    for i in sys.argv[1:]:
        jid = int(i)
        vlst=analyse_job(jid)
        plot_job(jid)
        for f, vsl in vlst:
            for vs in vsl:
                print('    %20s' % vs[0], '%(Period)12.6f %(min)6.2f - %(max)6.2f ' % vs[1])
else :
    for jid in brt.get_obs_list(dt=1):
        obs=brt.get_job(jid)
        if obs['filter'] not in set(('BVR','B','V','R','Blue', 'Green', 'Red', 'Colour')):
            continue
        vlst=analyse_job(obs)
        empty=True
        for f, vsl in vlst:
            for vs in vsl:
                vsname = vs[0].upper().split()
                if len(vsname[-1]) != 3 and len(vsname) != 2:
                    continue
                if not vsre.match(vsname[0]) :
                    continue
                empty = False
                print('    %20s' % vs[0], '%(Period)12.6f %(min)6.2f - %(max)6.2f ' % vs[1])
                sq = get_VS_sequence(vs[0])
            #plot_frame(f,vsl)
            if not empty : print()

        


