#!/usr/bin/python

import sys 
import mechanicalsoup
from lxml import etree

mech = mechanicalsoup.StatefulBrowser(soup_config={'features': 'lxml'})

#print >> sys.stderr, "Get sequence for >>%s<<" % (" ".join(sys.argv[1:]),)

tele=sys.argv[1]

if tele[0]=="G" :
    fov=90
else :
    fov=300

url="http://www.aavso.org/cgi-bin/vsp.pl?name=%s&ccdtable=on&fov=%d" % ("%20".join(sys.argv[2:]),fov)
page = mech.open(url)
html = ''.join([str(ln) for ln in page.soup])
page.close()
parser=etree.HTMLParser()
#tree=etree.parse(open('rcp/sekw.html'),parser)
tree=etree.fromstring(html,parser)

#print >> sys.stderr, html

def prtMag(m):
    m=m.split()
    if m[0]=='-' :
        return None
    v=float(m[0])
    try :
        e=float(m[1][1:-1])
    except ValueError:
        e=0.0
    return '%f/%f' % (v,e)

try :
    var=tree.xpath('//p[1]//text()')[1]
    ra=tree.xpath('//p[2]//text()')[1].split()[0]
    dec=tree.xpath('//p[2]//text()')[3].split()[0]
except IndexError :
    sys.exit(0)
    
dsgn=['u', 'b', 'v', 'rc', 'ic']

stars=[]

#print 'Variable:', var, ra, dec

for tab in tree.xpath('//table')[0:1]:
    seq=tab.xpath('./tr[last()]/td//text()')[1]
    #print >> sys.stderr, 'Sequence:', seq
    for row in tab.xpath('./tr')[1:-2]:
        c=row.xpath('./td/*/text()')
        lbl=row.xpath('./td//text()')[6]
        ra=row.xpath('./td/*/text()')[1].split()[0]
        dec=row.xpath('./td/*/text()')[2].split()[0]
        #print lbl, c[0], ra, dec, 
#        for d,m in zip(dsgn, (c[4], c[5], c[6], c[8], c[9])):
#            s=prtMag(m)
#            if s :
#                print '%s=%s' % (d,s),
        #print c[-1]
        stars.append([lbl," ".join(c[0].split()), ra, dec, c[4], c[5], c[6], c[8], c[9], c[-1]])
        #print c
        #print lbl, "ID:%s U:%s B:%s V:%s Rc:%s Ic:%s Cmnt:%s" %(c[0], c[4], c[5], c[6], c[8], c[9],c[-1])

ra=tree.xpath('//p[2]//text()')[1].split()[0]
dec=tree.xpath('//p[2]//text()')[3].split()[0]

print(var, ra, dec, seq, fov, file=sys.stderr)


print( '''( recipy ( object "%s" ra "%s" dec "%s" 
    equinox 2000 comments "From AAVSO VSP" ) 
  sequence "%s" 
  stars (
''' % (var, ra, dec, seq))

for s in stars:
    print( '''(name "%s" type std mag %f 
           ra "%s" dec "%s" 
           comments "AAVSO seq std, %s, %s" 
           smags "''' % (s[1],float(s[0])/10, s[2], s[3], s[0], s[-1].encode('ascii', 'ignore')), end='' )
    for d,m in zip(dsgn,s[4:-1]):
            v=prtMag(m)
            if v :
                print('%s(aavso)=%s' % (d,v), end='')
    print('''"
        flags ( ) )''')

print( '''(name "%s" type target 
    ra "%s" dec "%s" 
    flags ( var ) ) ) 
  )''' % (var, ra, dec) )


