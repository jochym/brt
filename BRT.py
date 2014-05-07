#!/usr/bin/python

# coding: utf-8

from __future__ import print_function, division

from requests import session
from BeautifulSoup import BeautifulSoup
from StringIO import StringIO
from zipfile import ZipFile
import time
from os import path

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




class Telescope :
    
    url='http://www.telescope.org/'
    
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

    def get_obs_list(self, t=None, dt=1):
        '''Get the dt days of observations taken no later then t. 

            Input
            ------
            t  - end time in seconds from the epoch (as returned by time.time())
            dt - number of days, default to 1

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

        searchdat = {
            'sort1':'completetime',
            'sort1order':'desc',
            'searchearliestcom[]':[d, m, y, '16','0'],
            'searchlatestcom[]':  [de,me,ye,'16','0'],
            'searchstatus[]':['1'],
            'resultsperpage':'200',
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

        


