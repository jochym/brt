#!/usr/bin/env python

import mechanicalsoup
from lxml import etree
from math import sqrt
mech = mechanicalsoup.StatefulBrowser(soup_config={'features': 'lxml'})

#print >> sys.stderr, "Get sequence for >>%s<<" % (" ".join(sys.argv[1:]),)


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

dsgn=['u', 'b', 'v', 'rc', 'ic']


def get_VS_sequence(vs, fov=60, maglimit=17):
    fov*=sqrt(2)
    url="http://www.aavso.org/cgi-bin/vsp.pl?name=%s&ccdtable=on&fov=%d" % ("%20".join(vs.split()),fov)
    url="https://www.aavso.org/apps/vsp/photometry/?fov=%.1f&star=%s&Rc=on&B=on&maglimit=%.1f" % ( fov,
            '+'.join(vs.split()), maglimit)
    page = mech.open(url)
    html = ''.join([str(ln) for ln in page.soup])
    page.close()
    parser=etree.HTMLParser()
    #tree=etree.parse(open('rcp/sekw.html'),parser)
    tree=etree.fromstring(html,parser)

    try :
        var=' '.join(tree.xpath('//p//strong//text()')[0].split()[1:])
        ra=tree.xpath('//p//strong//text()')[1].split()[0]
        dec=tree.xpath('//p//strong//text()')[2].split()[0]
        seq=tree.xpath('//p//strong//text()')[3]
    except IndexError :
        #print('Cannot get AAVSO sequence for', vs)
        return None, None

    stars=[]

    #print('\nSequence %s for: %s ( ra: %s  dec: %s )' % (seq, var, ra, dec), file=sys.stderr)

    for tab in tree.xpath('//table//tbody')[0:1]:
        #print >> sys.stderr, 'Sequence:', seq
        for row in tab.xpath('./tr')[1:-2]:
            c=row.xpath('./td/text()')
            auid=c[0]
            lbl=row.xpath('./td/strong/text()')[0]
            ra=c[1].split()[0]
            ra_flt=float(c[1].split()[1][1:-2])
            dec=c[2].split()[0]
            dec_flt=float(c[1].split()[1][1:-2])
            #print(c, file=sys.stderr)
            #print(auid, lbl, ra, ra_flt, dec, dec_flt, file=sys.stderr)
    #        for d,m in zip(dsgn, (c[4], c[5], c[6], c[8], c[9])):
    #            s=prtMag(m)
    #            if s :
    #                print '%s=%s' % (d,s),
            #print c[-1]
            stars.append([auid, lbl, ra, ra_flt, dec, dec_flt] +
                        [v  for v in c[3:7]])
            #print c
            #print lbl, "ID:%s U:%s B:%s V:%s Rc:%s Ic:%s Cmnt:%s" %(c[0], c[4], c[5], c[6], c[8], c[9],c[-1])

    #print(' ', seq, fov, file=sys.stderr)
    return seq, stars

