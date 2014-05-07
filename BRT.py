#!/usr/bin/python

# coding: utf-8

from requests import session
from BeautifulSoup import BeautifulSoup
import time


class Telescope :
    
    url='http://www.telescope.org/'
    
    def __init__(self,user,passwd):
        self.s=None
        self.user=user
        self.passwd=passwd
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

        print '%d/%d/%d -> %d/%d/%d' % (d,m,y,de,me,ye)

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
        



