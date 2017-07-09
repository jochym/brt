#!/usr/bin/env python

# coding: utf-8

from __future__ import print_function, division, absolute_import

import os, tempfile, shutil
from requests import session
import requests
from bs4 import BeautifulSoup
from io import StringIO, BytesIO
from zipfile import ZipFile, BadZipFile
import time
from os import path

import diskcache

from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy.time import Time

global DEBUG

DEBUG=1

def debug_prn(*args,**kwargs):
    if kwargs['lvl'] <= DEBUG:
        print(*args)
        
def debug(*args):
    debug_prn('DEBUG:',*args,lvl=5)

def info(*args):
    debug_prn(' INFO:',*args,lvl=2)
    
def warning(*args):
    debug_prn(' WARN:',*args,lvl=1)

def error(*args):
    debug_prn('ERROR:',*args,lvl=0)


def cleanup(s):
    return s.encode('ascii','ignore').decode('ascii','ignore')


# TODO: Cache the downloads to not re-download the same data again if possible.
# TODO: Better error handling.

class Telescope :
    
    url='http://www.telescope.org/'
    cameratypes={
        'constellation':'1',
        'galaxy':       '2',
        'cluster':      '3',
        'planet':'5',
        'coast':'6',
        'pirate':'7',
    }
    
    def __init__(self,user,passwd,cache='.cache/jobs'):
        self.s=None
        self.user=user
        self.passwd=passwd
        self.tout=60
        self.retry=15
        self.login()
        self.cache=cache
        
    def login(self):
        payload = {'action': 'login',
                   'username': self.user,
                   'password': self.passwd,
                   'stayloggedin': 'true'}
            
        debug('Get session ...')
        self.s=session()
        debug('Logging in ...')
        self.s.post(self.url+'login.php', data=payload)

    def logout(self):
        if self.s==None :
            self.s.post(self.url+'logout.php')
            self.s=None

    def get_obs_list(self, t=None, dt=1, filtertype='', camera='', hour=16, minute=0):
        '''Get the dt days of observations taken no later then time in t. 

            Input
            ------
            t  - end time in seconds from the epoch 
                (as returned by time.time())
            dt - number of days, default to 1
            filtertype - filter by type of filter used
            camera - filter by the camera/telescope used

            Output
            ------
            Returns a list of JobIDs (int) for the observations.

        '''

        assert(self.s != None)
        
        if t==None :
            t=time.time()-time.timezone


        st=time.gmtime(t-86400*dt)
        et=time.gmtime(t)

        d=st.tm_mday
        m=st.tm_mon
        y=st.tm_year
        de=et.tm_mday
        me=et.tm_mon
        ye=et.tm_year

        debug('%d/%d/%d -> %d/%d/%d' % (d,m,y,de,me,ye))

        try :
            telescope=self.cameratypes[camera.lower()]
        except KeyError:
            telescope=''

        searchdat = {
            'sort1':'completetime',
            'sort1order':'desc',
            'searchearliestcom[]':[d, m, y, str(hour),str(minute)],
            'searchlatestcom[]':  [de,me,ye,str(hour),str(minute)],
            'searchstatus[]':['1'],
            'resultsperpage':'200',
            'searchfilter':filtertype,
            'searchtelescope':telescope,
            'submit':'Go'
        }

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}


        request = self.s.post(self.url+'v3job-search-query.php',
                         data=searchdat, headers=headers)
        soup = BeautifulSoup(request.text,'lxml')

        jlst=[]
        for l in soup.findAll('tr'):
            try :
                a=l.find('a').get('href')
            except AttributeError :
                continue
            jid=a.rfind('jid')
            if jid>0 :
                jid=a[jid+4:].split('&')[0]
                jlst.append(int(jid))
        return jlst
    
    def get_job(self,jid=None):
        '''Get a job data for a given JID'''
        
        assert(jid!=None)
        assert(self.s != None)
        
        obs={}
        debug(jid)
        obs['jid']=jid
        rq=self.s.post(self.url+('v3cjob-view.php?jid=%d' % jid))
        soup = BeautifulSoup(rq.text, 'lxml')
        for l in soup.findAll('tr'):
            debug(cleanup(l.text))
            txt=''
            for f in l.findAll('td'):
                if txt.find('Object Type') >= 0:
                    obs['type']=f.text
                if txt.find('Object ID') >= 0:
                    obs['oid']=f.text
                if txt.find('Telescope Type Name') >= 0:
                    obs['tele']=f.text
                if txt.find('Filter Type') >= 0:
                    obs['filter']=f.text
                if txt.find('Exposure Time') >= 0:
                    obs['exp']=f.text
                if txt.find('Completion Time') >= 0:
                    t=f.text.split()
                    obs['completion']=t[3:6]+[t[6][1:]]+[t[7][:-1]]
                if txt.find('Status') >= 0:
                    obs['status']= (f.text == 'Success')

                txt=f.text
        info('%(jid)d [%(tele)s, %(filter)s, %(status)s]: %(type)s %(oid)s %(exp)s' % obs)
        
        return obs

        
    def download_obs(self,obs=None, directory='.', cube=False):
        '''Download the raw observation obs (obtained from get_job) into zip 
        file named job_jid.zip located in the directory (current by default).
        Alternatively, when the cube=True the file will be a 3D fits file.
        The name of the file (without directory) is returned.'''
        
        assert(obs!=None)
        assert(self.s != None)
        
        jid=obs['jid']
        
        rq=self.s.get(self.url+
                      ('v3image-download%s.php?jid=%d' % 
                        ('' if cube else '-layers', obs['jid'])),
                      stream=True)
                      
        fn = ('%(jid)d.' % obs) + ('fits' if cube else 'zip')
        with open(path.join(directory, fn), 'wb') as fd:
            for chunk in rq.iter_content(512):
                fd.write(chunk)
        return fn


    def get_obs(self,obs=None, cube=False, recurse=True):
        '''Get the raw observation obs (obtained from get_job) into zip 
        file-like object. The function returns ZipFile structure of the 
        downloaded data.'''
        
        assert(obs!=None)
        assert(self.s != None)
        
        fn = ('%(jid)d.' % obs) + ('fits' if cube else 'zip')
        fp = path.join(self.cache,fn[0],fn[1],fn)
        if not path.isfile(fp) :
            info('Getting %s from server' % fp)
            os.makedirs(path.dirname(fp), exist_ok=True)
            self.download_obs(obs,path.dirname(fp),cube)
        else :
            info('Getting %s from cache' % fp)
        content = open(fp,'rb')
        try :
            return content if cube else ZipFile(content)
        except zipfile.BadZipFile :
            # Probably corrupted download. Try again once.
            content.close()
            os.remove(fp)
            if recurse :
                return self.get_obs(obs, cube, False)
            else :
                return None

    def download_obs_processed(self,obs=None, directory='.', cube=False):
        '''Download the raw observation obs (obtained from get_job) into zip 
        file named job_jid.zip located in the directory (current by default).
        Alternatively, when the cube=True the file will be a 3D fits file.
        The name of the file (without directory) is returned.'''
        
        assert(obs!=None)
        assert(self.s != None)
        
        fn=None
        
        jid=obs['jid']

        tout=self.tout

        while tout > 0 :
            rq=self.s.get(self.url+
                          ('imageengine-request.php?jid=%d&type=%d' % 
                            (obs['jid'], 1 if cube else 3 )))

            soup = BeautifulSoup(rq.text, 'lxml')
            dlif=soup.find('iframe')
            
            try :
                dl=dlif.get('src')
                rq=self.s.get(self.url+dl,stream=True)
                
                fn = ('brt_%(jid)d.' % obs) + ('fits' if cube else 'zip')
                with open(path.join(directory, fn), 'wb') as fd:
                    for chunk in rq.iter_content(512):
                        fd.write(chunk)
                return fn
            except AttributeError :
                tout-=self.retry
                warning('No data. Sleep for %ds ...'%self.retry)
                time.sleep(self.retry)
            
        return None


    def get_obs_processed(self,obs=None, cube=False):
        '''Get the raw observation obs (obtained from get_job) into zip 
        file-like object. The function returns ZipFile structure of the 
        downloaded data.'''
        
        assert(obs!=None)
        assert(self.s != None)
        
        fn=None
        
        jid=obs['jid']

        tout=self.tout

        while tout > 0 :
            rq=self.s.get(self.url+
                          ('imageengine-request.php?jid=%d&type=%d' % 
                            (obs['jid'], 1 if cube else 3 )))

            soup = BeautifulSoup(rq.text,'lxml')
            dlif=soup.find('iframe')
            
            try :
                dl=dlif.get('src')
                rq=self.s.get(self.url+dl,stream=True)
                return StringIO(rq.content) if cube else ZipFile(StringIO(rq.content))
                
            except AttributeError :
                tout-=self.retry
                warning('No data. Sleep for %ds ...'%self.retry)
                time.sleep(self.retry)
            
        return None

    def extractTicket(self,rq):
        soup = BeautifulSoup(rq.text, 'lxml')
        t=int(soup.find('input', attrs={
                        'name':'ticket',
                        'type':'hidden'})['value'])
        debug('Ticket:', t)
        return t


    def submitRADECjob(self, obj, exposure=30000, tele='COAST', 
                        filt='BVR', darkframe=True, 
                        name='RaDec object', comment='AutoSubmit'):
        assert(self.s != None)
        ra=obj.ra.to_string(unit='hour', sep=' ',
                            pad=True, precision=2,
                            alwayssign=False).split()
        dec=obj.dec.to_string(sep=' ', 
                            pad=True, precision=2, 
                            alwayssign=True).split()
        try :
            tele=self.cameratypes[tele.lower()]
        except KeyError :
            debug('Wrong telescope:', tele, 'selecting COAST(6)')
            tele=6
            
        if tele==7 :
            if filt=='BVR' : filt='Colour'
            if filt=='B' : filt='Blue'
            if filt=='V' : filt='Green'
            if filt=='R' : filt='Red'
        if tele==6 :
            if filt=='Colour' : filt='BVR'
            if filt=='Blue' : filt='B'
            if filt=='Green' : filt='V'
            if filt=='Red' : filt='R'
            
        u=self.url+'/request-constructor.php'
        r=self.s.get(u+'?action=new')
        t=self.extractTicket(r)
        debug('GoTo Part 1', t)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part1'})
        t=self.extractTicket(r)
        debug('GoTo RADEC', t)
        r=self.s.post(u,data={'ticket':t,'action':'part1-go-radec'})
        t=self.extractTicket(r)
        debug('Save RADEC', t)
        r=self.s.post(u,data={'ticket':t,'action':'part1-radec-save',
                             'raHours':ra[0],
                             'raMins':ra[1],
                             'raSecs':ra[2].split('.')[0],
                             'raFract':ra[2].split('.')[1],
                             'decDegrees':dec[0],
                             'decMins':dec[1],
                             'decSecs':dec[2].split('.')[0],
                             'decFract':dec[2].split('.')[1],
                             'newObjectName':name})
        t=self.extractTicket(r)
        debug('GoTo Part 2', t)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part2'})
        t=self.extractTicket(r)
        debug('Save Telescope', t)
        r=self.s.post(u,data={'ticket':t, 
                                'action':'part2-save', 
                                'submittype':'Save',
                                'newTelescopeSelection':tele})
        t=self.extractTicket(r)
        debug('GoTo Part 3')
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part3'})
        t=self.extractTicket(r)
        debug('Save Exposure')
        r=self.s.post(u,data={'ticket':t, 
                                'action':'part3-save', 
                                'submittype':'Save',
                                'newExposureTime':exposure,
                                'newDarkFrame': 1 if darkframe else 0,
                                'newFilterSelection':filt,
                                'newRequestComments':comment})
        t=self.extractTicket(r)
        debug('Submit', t)
        r=self.s.post(u,data={'ticket':t, 'action':'main-submit'})
        return r
        
    def submitVarStar(self, name, expos=90, filt='BVR',comm='', tele='COAST'):
        o=SkyCoord.from_name(name)
        return self.submitRADECjob(o, name=name, comment=comm, 
                                exposure=expos*1000, filt=filt, tele=tele)


def getFrameRaDec(hdu):
    if 'OBJCTRA' in hdu.header:
        ra=hdu.header['OBJCTRA']
        dec=hdu.header['OBJCTDEC']
    elif 'MNTRA' in hdu.header :
        ra=hdu.header['MNTRA']
        dec=hdu.header['MNTDEC']        
    elif 'RA-TEL' in hdu.header :
        ra=hdu.header['RA-TEL']
        dec=hdu.header['DEC-TEL']                
    else :
        raise KeyError
    
    try :
        eq=Time(hdu.header['EQUINOX'], format='decimalyear')
    except KeyError :
        eq=Time(2000, format='decimalyear')
    
    o=SkyCoord(Longitude(ra, unit='hour'),
               Latitude(dec, unit='deg'),
               frame='icrs', obstime=hdu.header['DATE-OBS'], 
               equinox=eq)
    return o


astrometry_cmd='solve-field -p -z 2 -l 15 -O -L %d -H %d -u app -3 %f -4 %f -5 5 %s'
telescopes={
    'galaxy':   (1,2),
    'cluster':  (14,16),
    'coast': (1, 2),
    'pirate': (1, 2),
}

def _solveField_local(hdu, cleanup=True):
    o=getFrameRaDec(hdu)
    ra=o.ra.deg
    dec=o.dec.deg
    tel = hdu.header['TELESCOP'].lower()
    if 'brt' in tel:
        tel=tel.split()[1]
    else :
        tel=tel.split()[0]
        
    loapp, hiapp=telescopes[tel]
    td=tempfile.mkdtemp(prefix='field-solver')
    try :
        fn=tempfile.mkstemp(dir=td, suffix='.fits')
        debug(td, fn)
        hdu.writeto(fn[1])
        debug((astrometry_cmd % (loapp, hiapp, ra, dec, fn[1])))
        solver=os.popen(astrometry_cmd % (loapp, hiapp, ra, dec, fn[1]))
        for ln in solver:
            debug(ln.strip())
        shdu=fits.open(BytesIO(open(fn[1][:-5]+'.new','rb').read()))
        return shdu
    except IOError :
        return None
    finally :
        if cleanup :
            shutil.rmtree(td)

from am import Client

astrometryAPIkey=None

def _solveField_remote(hdu, name='brtjob', apikey=None, apiurl='http://nova.astrometry.net/api/', cleanup=True):
    if apikey is None :
        if astrometryAPIkey is None :
            print('You need an API key from astrometry.net to use network solver.')
            return None
        else :
            apikey=astrometryAPIkey
    cli=Client()
    cli.login(apikey)
    bio=BytesIO()
    hdu.writeto(bio)
    bio.seek(0)
    res=cli.send_request('upload',{},(name,bio.read()))

    while True:
        stat = cli.sub_status(res['subid'], justdict=True)
        debug('Got status:', stat)
        jobs = stat.get('jobs', [])
        if len(jobs):
            for j in jobs:
                if j is not None:
                    break
            if j is not None:
                debug('Selecting job id', j)
                job_id = j
                break
        time.sleep(5)

    success = False
    while True:
        stat = cli.job_status(job_id, justdict=True)
        debug('Got job status:', stat)
        if stat.get('status','') in ['success']:
            success = (stat['status'] == 'success')
            break
        time.sleep(5)

    if success:
        cli.job_status(job_id)
        # result = c.send_request('jobs/%s/calibration' % opt.job_id)
        # dprint('Calibration:', result)
        # result = c.send_request('jobs/%s/tags' % opt.job_id)
        # dprint('Tags:', result)
        # result = c.send_request('jobs/%s/machine_tags' % opt.job_id)
        # dprint('Machine Tags:', result)
        # result = c.send_request('jobs/%s/objects_in_field' % opt.job_id)
        # dprint('Objects in field:', result)
        #result = c.send_request('jobs/%s/annotations' % opt.job_id)
        #dprint('Annotations:', result)

        # We don't need the API for file retrival, just construct URL
        url = apiurl.replace('/api/', '/new_fits_file/%i' % job_id)

        debug('Retrieving file from', url)
        r = requests.get(url)
        shdu=fits.open(BytesIO(r.content))
    
    return shdu

def solveField(hdu, name='brtjob', local=None, apikey=None, apiurl='http://nova.astrometry.net/api/', cleanup=True):
    '''
    Solve plate using local or remote (nova.astrometry.net) plate solver.
    '''
    if local==True :
        return _solveField_local(hdu, cleanup=cleanup)
    elif local==False :
        return _solveField_remote(hdu, name=name, apikey=apikey, apiurl=apiurl, cleanup=cleanup)
    elif local is None :
        shdu = _solveField_local(hdu)
        if shdu is None :
            print('Local solver failed. Trying remote ...')
            shdu = _solveField_remote(hdu, name=name, apikey=apikey, apiurl=apiurl)
        return shdu
