#!/usr/bin/env python

# coding: utf-8

from __future__ import print_function, division, absolute_import

import os, tempfile, shutil
from requests import session
import requests
from bs4 import BeautifulSoup
import json
from io import StringIO, BytesIO
from zipfile import ZipFile, BadZipFile
import time
from os import path

from astropy.io import fits
from astropy.coordinates import SkyCoord, Longitude, Latitude
from astropy.time import Time

import logging

def cleanup(s):
    return s.encode('ascii','ignore').decode('ascii','ignore')


# TODO: Cache the downloads to not re-download the same data again if possible.
# TODO: Better error handling.

class Telescope :

    url='https://www.telescope.org/'
    cameratypes={
        'constellation':'1',
        'galaxy':       '2',
        'cluster':      '3',
        'planet':'5',
        'coast':'6',
        'pirate':'7',
    }

    REQUESTSTATUS_TEXTS={
        1: "New",
        2: "New, allocated",
        3: "Waiting",
        4: "In progress",
        5: "Reallocate",
        6: "Waiting again",
        7: "Complete on site",
        8: "Complete",
        9: "Hold",
        10: "Frozen",
        20: "Expired",
        21: "Expired w/CJobs",
        22: "Cancelled",
        23: "Cancelled w/CJobs",
        24: "Invalid",
        25: "Never rises",
        26: "Other error",
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
        log = logging.getLogger(__name__)
        payload = {'action': 'login',
                   'username': self.user,
                   'password': self.passwd,
                   'stayloggedin': 'true'}
        log.debug('Get session ...')
        self.s=session()
        log.debug('Logging in ...')
        self.s.post(self.url+'login.php', data=payload)

    def logout(self):
        if self.s is None :
            self.s.post(self.url+'logout.php')
            self.s=None

    def get_user_requests(self, sort='rid', folder=1):
        '''
        Get all user requests from folder (Inbox=1 by default),
        sorted by sort column ('rid' by default). 
        Possible sort columns are: 'rid', 'object', 'completion'
        The data is returned as a list of dictionaries.
        '''

        #fetch first batch        
        params={
            'limit': 100,
            'sort': sort,
            'folderid': folder}

        rq = self.s.post(self.url+"api-user.php", {'module': "request-manager", 
                                                   'request': "1-get-list-own",
                                                   'params' : json.dumps(params)})
        res=[]
        dat=json.loads(rq.content)
        total=int(dat['data']['totalRequests'])
        res+=dat['data']['requests']

        # Fetch the rest
        params['limit']=total-len(res)
        params['startAfterRow']=len(res)
        rq = self.s.post(self.url+"api-user.php", {'module': "request-manager", 
                                                   'request': "1-get-list-own",
                                                   'params' : json.dumps(params)})

        dat=json.loads(rq.content)
        total=int(dat['data']['totalRequests'])
        res+=dat['data']['requests']
        return res


    def get_user_folders(self):
        '''
        Get all user folders. Returns list of dictionaries.
        '''
        rq = self.s.post(self.url+"api-user.php", {'module': "request-manager", 
                                                   'request': "0-get-my-folders"})
        return json.loads(rq.content)['data']


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

        assert(self.s is not None)

        if t is None :
            t=time.time()-time.timezone


        st=time.gmtime(t-86400*dt)
        et=time.gmtime(t)

        d=st.tm_mday
        m=st.tm_mon
        y=st.tm_year
        de=et.tm_mday
        me=et.tm_mon
        ye=et.tm_year

        log = logging.getLogger(__name__)
        log.debug('%d/%d/%d -> %d/%d/%d', d,m,y,de,me,ye)

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
            'resultsperpage':'1000',
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

        assert(jid is not None)
        assert(self.s is not None)

        log = logging.getLogger(__name__)
        log.debug(jid)

        obs={}
        obs['jid']=jid
        rq=self.s.post(self.url+('v3cjob-view.php?jid=%d' % jid))
        soup = BeautifulSoup(rq.text, 'lxml')
        for l in soup.findAll('tr'):
            log.debug(cleanup(l.text))
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
        log.info('%(jid)d [%(tele)s, %(filter)s, %(status)s]: %(type)s %(oid)s %(exp)s', obs)

        return obs


    def download_obs(self,obs=None, directory='.', cube=False):
        '''Download the raw observation obs (obtained from get_job) into zip
        file named job_jid.zip located in the directory (current by default).
        Alternatively, when the cube=True the file will be a 3D fits file.
        The name of the file (without directory) is returned.'''

        assert(obs is not None)
        assert(self.s is not None)

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

        assert(obs is not None)
        assert(self.s is not None)

        log = logging.getLogger(__name__)

        fn = ('%(jid)d.' % obs) + ('fits' if cube else 'zip')
        fp = path.join(self.cache,fn[0],fn[1],fn)
        if not path.isfile(fp) :
            log.info('Getting %s from server', fp)
            os.makedirs(path.dirname(fp), exist_ok=True)
            self.download_obs(obs,path.dirname(fp),cube)
        else :
            log.info('Getting %s from cache', fp)
        content = open(fp,'rb')
        try :
            return content if cube else ZipFile(content)
        except BadZipFile :
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

        assert(obs is not None)
        assert(self.s is not None)

        log = logging.getLogger(__name__)

        fn=None

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
                log.warning('No data. Sleep for %ds ...'%self.retry)
                time.sleep(self.retry)

        return None


    def get_obs_processed(self,obs=None, cube=False):
        '''Get the raw observation obs (obtained from get_job) into zip
        file-like object. The function returns ZipFile structure of the
        downloaded data.'''

        assert(obs is not None)
        assert(self.s is not None)
        log = logging.getLogger(__name__)

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
                log.warning('No data. Sleep for %ds ...'%self.retry)
                time.sleep(self.retry)

        return None

    @staticmethod
    def extract_ticket(rq):
        soup = BeautifulSoup(rq.text, 'lxml')
        t=int(soup.find('input', attrs={
                        'name':'ticket',
                        'type':'hidden'})['value'])
        log = logging.getLogger(__name__)
        log.debug('Ticket: %s', t)
        return t


    def do_api_call(self, module, req, params=None):
        rq = self.s.post(self.url+"api-user.php", {'module': module,
                                                   'request': req,
                                                   'params': {} if params is None else json.dumps(params)})
        return json.loads(rq.content)

    def do_rm_api(self, req, params=None):
        return self.do_api_call("request-manager", req, params)


    def do_rc_api(self, req, params=None):
        return self.do_api_call("request-constructor", req, params)


    def submit_job_api(self, obj, exposure=30000, tele='COAST',
                        filt='BVR', darkframe=True,
                        name='RaDec object', comment='AutoSubmit'):
        assert(self.s is not None)

        log = logging.getLogger(__name__)

        ra=obj.ra.to_string(unit='hour', sep=':', pad=True, precision=2,
                            alwayssign=False)
        dec=obj.dec.to_string(sep=':', pad=True, precision=2,
                            alwayssign=True)
        try :
            tele=self.cameratypes[tele.lower()]
        except KeyError :
            log.warning('Wrong telescope: %d ; selecting COAST(6)', tele)
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

        params = {'telescopeid': tele, 'telescopetype': 2,
                  'exposuretime': exposure, 'filtertype': filt,
                  'objecttype': 'RADEC', 'objectname': name,
                  'objectid': ra+' '+dec, 'usercomments': comment }

        self.do_rc_api("0-rb-clear")

        r = self.do_rc_api("0-rb-set", params)
        log.debug('Req data:%s', r)
        if r['success'] :
            r = self.do_rc_api("0-rb-submit")
            log.debug('Submission data:%s', r)
        if r['success'] :
            return True, r['data']['id']
        else :
            log.warning('Submission error. Status:%s', r['status'])
            return False, r['status']


    def submit_RADEC_job(self, obj, exposure=30000, tele='COAST',
                        filt='BVR', darkframe=True,
                        name='RaDec object', comment='AutoSubmit'):
        assert(self.s is not None)

        log = logging.getLogger(__name__)

        ra=obj.ra.to_string(unit='hour', sep=' ',
                            pad=True, precision=2,
                            alwayssign=False).split()
        dec=obj.dec.to_string(sep=' ',
                            pad=True, precision=2,
                            alwayssign=True).split()
        try :
            tele=self.cameratypes[tele.lower()]
        except KeyError :
            log.warning('Wrong telescope: %d ; selecting COAST(6)', tele)
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
        t=self.extract_ticket(r)
        log.debug('GoTo Part 1 (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part1'})
        t=self.extract_ticket(r)
        log.debug('GoTo RADEC (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,'action':'part1-go-radec'})
        t=self.extract_ticket(r)
        log.debug('Save RADEC (ticket %s)', t)
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
        t=self.extract_ticket(r)
        log.debug('GoTo Part 2 (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part2'})
        t=self.extract_ticket(r)
        log.debug('Save Telescope (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,
                                'action':'part2-save',
                                'submittype':'Save',
                                'newTelescopeSelection':tele})
        t=self.extract_ticket(r)
        log.debug('GoTo Part 3 (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,'action':'main-go-part3'})
        t=self.extract_ticket(r)
        log.debug('Save Exposure (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t,
                                'action':'part3-save',
                                'submittype':'Save',
                                'newExposureTime':exposure,
                                'newDarkFrame': 1 if darkframe else 0,
                                'newFilterSelection':filt,
                                'newRequestComments':comment})
        t=self.extract_ticket(r)
        log.debug('Submit (ticket %s)', t)
        r=self.s.post(u,data={'ticket':t, 'action':'main-submit'})
        return r

    def submitVarStar(self, name, expos=90, filt='BVR',comm='', tele='COAST'):
        o=SkyCoord.from_name(name)
        return self.submit_job_api(o, name=name, comment=comm,
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
    log = logging.getLogger(__name__)

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
        log.debug(td, fn)
        hdu.writeto(fn[1])
        log.debug((astrometry_cmd % (loapp, hiapp, ra, dec, fn[1])))
        solver=os.popen(astrometry_cmd % (loapp, hiapp, ra, dec, fn[1]))
        for ln in solver:
            log.debug(ln.strip())
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
    log = logging.getLogger(__name__)

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
        log.debug('Got status: %s', stat)
        jobs = stat.get('jobs', [])
        if len(jobs):
            for j in jobs:
                if j is not None:
                    break
            if j is not None:
                log.debug('Selecting job id %d', j)
                job_id = j
                break
        time.sleep(5)

    success = False
    while True:
        stat = cli.job_status(job_id, justdict=True)
        log.debug('Got job status: %s', stat)
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

        log.debug('Retrieving file from %s', url)
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
