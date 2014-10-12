#!/usr/bin/python

# coding: utf-8

from __future__ import print_function, division

from requests import session
from bs4 import BeautifulSoup
from StringIO import StringIO
from zipfile import ZipFile
import time
from os import path

from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from urllib2 import urlopen

global DEBUG

DEBUG=1

def debug_prn(*args,**kwargs):
    if kwargs['lvl'] <= DEBUG:
        print(*args)
        
def info(*args):
    debug_prn(' INFO:',*args,lvl=5)
    
def debug(*args):
    debug_prn('DEBUG:',*args,lvl=4)
    
def warning(*args):
    debug_prn(' WARN:',*args,lvl=1)

def error(*args):
    debug_prn('ERROR:',*args,lvl=0)


# TODO: Cache the downloads to not re-download the same data again if possible.
# TODO: Better error handling.

class Telescope :
    
    url='http://www.telescope.org/'
    cameratypes={'Galaxy':'2',
                'Cluster':'3',
                'Constellation':'1',
                'Planet':'5'}
    
    def __init__(self,user,passwd):
        self.s=None
        self.user=user
        self.passwd=passwd
        self.tout=60
        self.retry=15
        self.login()
        
    def login(self):
        payload = {'action': 'login',
                   'username': self.user,
                   'password': self.passwd,
                   'stayloggedin': 'true'}
            
        self.s=session()
        self.s.post(self.url+'login.php', data=payload)

    def logout(self):
        if self.s==None :
            self.s.post(self.url+'logout.php')
            self.s=None

    def get_obs_list(self, t=None, dt=1, filtertype='', camera=''):
        '''Get the dt days of observations taken no later then t. 

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
            t=time.time()


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
            telescope=self.cameratypes[camera]
        except KeyError:
            telescope=''

        searchdat = {
            'sort1':'completetime',
            'sort1order':'desc',
            'searchearliestcom[]':[d, m, y, '16','0'],
            'searchlatestcom[]':  [de,me,ye,'16','0'],
            'searchstatus[]':['1'],
            'resultsperpage':'200',
            'searchfilter':filtertype,
            'searchtelescope':telescope,
            'submit':'Go'
        }

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}


        request = self.s.post(self.url+'v3job-search-query.php',
                         data=searchdat, headers=headers)
        soup = BeautifulSoup(request.text)

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
        #print jid
        obs['jid']=jid
        rq=self.s.post(self.url+('v3cjob-view.php?jid=%d' % jid))
        soup = BeautifulSoup(rq.text)
        for l in soup.findAll('tr'):
            info(l)
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
        debug('%(jid)d [%(tele)s, %(filter)s, %(status)s]: %(type)s %(oid)s %(exp)s' % obs)
        
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
                      
        fn = ('job_%(jid)d.' % obs) + ('fits' if cube else 'zip')
        with open(path.join(directory, fn), 'wb') as fd:
            for chunk in rq.iter_content(512):
                fd.write(chunk)
        return fn


    def get_obs(self,obs=None, cube=False):
        '''Get the raw observation obs (obtained from get_job) into zip 
        file-like object. The function returns ZipFile structure of the 
        downloaded data.'''
        
        assert(obs!=None)
        assert(self.s != None)
        
        rq=self.s.get(self.url+
                      ('v3image-download%s.php?jid=%d' %
                       ('' if cube else '-layers', obs['jid'])),
                      stream=True)

        return StringIO(rq.content) if cube else ZipFile(StringIO(rq.content))


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

            soup = BeautifulSoup(rq.text)
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

            soup = BeautifulSoup(rq.text)
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
        soup = BeautifulSoup(rq.text)
        return int(soup.find('input', attrs={
                        'name':'ticket',
                        'type':'hidden'})['value'])


    def submitRADECjob(self, obj, exposure=1000, tele='Galaxy', 
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
            tele=self.cameratypes[tele]
        except KeyError :
            tele=2
        u=self.url+'/request-constructor.php'
        r=self.s.get(u+'?action=new')
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part1'})
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t,'action':'part1-go-radec'})
        t=self.extractTicket(r)
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
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part2'})
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t, 
                                'action':'part2-save', 
                                'submittype':'Save',
                                'newTelescopeSelection':tele})
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part3'})
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t, 
                                'action':'part3-save', 
                                'submittype':'Save',
                                'newExposureTime':exposure,
                                'newDarkFrame': 1 if darkframe else 0,
                                'newFilterSelection':filt,
                                'newRequestComments':comment})
        t=self.extractTicket(r)
        r=self.s.post(u,data={'ticket':t, 'action':'main-submit'})
        return r
        
    def submitVarStar(self, name, expos=60000, filt='BVR',comm=''):
        o=SkyCoord.from_name(name)
        self.submitRADECjob(o, name=name, comment=comm, 
                                exposure=expos, filt=filt)


def getFrameRaDec(hdu):
    try :
        o=SkyCoord(Longitude(hdu.header['OBJCTRA'], unit='hour'),
                   Latitude(hdu.header['OBJCTDEC'], unit='deg'),
                   frame='icrs', obstime=hdu.header['DATE-OBS'], 
                   equinox=hdu.header['EQUINOX'])
    except KeyError :
        try :
            o=SkyCoord(Longitude(hdu.header['MNTRA'], unit='hour'),
                   Latitude(hdu.header['MNTDEC'], unit='deg'),
                   frame='icrs', obstime=hdu.header['DATE-OBS'], 
                   equinox=hdu.header['EQUINOX'])
        except KeyError :
            raise
    return o

import os, tempfile, shutil
from StringIO import StringIO

astrometry_cmd='solve-field -2 -p -O -L %d -H %d -u app -3 %f -4 %f -5 5 %s'
telescopes={'Galaxy':   (1,2),
            'Cluster':  (14,16)}

def _solveField_local(hdu):
    o=getFrameRaDec(hdu)
    ra=o.ra.deg
    dec=o.dec.deg
    loapp, hiapp=telescopes[hdu.header['TELESCOP'].split()[1]]
    td=tempfile.mkdtemp(prefix='field-solver')
    try :
        fn=tempfile.mkstemp(dir=td, suffix='.fits')
        debug(td, fn)
        hdu.writeto(fn[1])
        debug((astrometry_cmd % (loapp, hiapp, ra, dec, fn[1])))
        solver=os.popen(astrometry_cmd % (loapp, hiapp, ra, dec, fn[1]))
        for ln in solver:
            debug(ln.strip())
        shdu=fits.open(StringIO(open(fn[1][:-5]+'.new').read()))
        return shdu
    except IOError :
        return None
    finally :
        shutil.rmtree(td)



def solveField(hdu, local=True, apikey=None, apiurl='http://nova.astrometry.net/api/'):
    '''
    Solve plate using local or remote (nova.astrometry.net) plate solver.
    '''
    if local :
        return _solveField_local(hdu)
    else :
        if apikey is None :
            print('You need an API key from astrometry.net to use network solver.')
            return None
        return _solveField_remote(hdu, apikey=apikey, apiurl=apiurl)
