#!/usr/bin/python
#
# bpdbreport.py
#
# Take input from bpdbjobs -report -all_columns
# and change info into human readable format
#
# Changelog:
#
# 2012-04-02:   JAP
#   Added/verified default compatability with NetBackup 7.1.x.
#      (technically 'frozenimage' became 'snapshot', but it's
#      a pretty small detail, so I have not 'fixed' it.
#   Added -ymd flag. Same as mdy, just with y first.
#   Added --show_backups option which omits all job_type != 0 and
#      where Sched == '-' (aka not Full/Differential/Cumulative)
#   Added --no_header.  Omitts the header line from output
#      (useful if using this script in a stdin/stdout chain)
#   Added the ability to parse 'try' data out of the bpdbjobs
#      output. This is the most 'invasive' code modification.
#      You can now specify 'try*' fields from a format file.
#      One line will be printed per try.  All other data will
#      be duplicated.
#      If you don't specify 'try' lines, there is no change.
#      Still one line per job.
# 2005-06-06:   DWR
#   Added output logic to determine whether the job data is
#   3.x, 4.x or 5.x. The header line is currently always a 5.x
#   header, the last fields just aren't used unless it is data
#   from a 5.x environment. Currently in testing mode.
# 2005-05-03:   DWR
#   Added logic to throw out lines that have embedded newline
#   characters in string values from the -most_columns output.
#   The csv module doesn't handle it very well. I still need to
#   figure out how to handle the broken lines for reporting.
# 2004-09-03:   DWR
#   Added "--hoursago","-q (quiet)", and "--shelv_dict" options
#   to help facilitate creating a dictionary for later retrieval
#   by a different python script.
# 2004-08-02:   DWR
#   Added try/except block around test for start/end time and for
#   which state the job is currently listed. Discovered that it is
#   possible for a job to exist with absolutely NO information.
# 2004-02-27:   DWR
#   Added basic framework for displaying all job entries, not just
#   jobs with a State of "Done". The two new switches are:
#   --show_all   (shows Active,Done,Queued,Re-Queued)
#   --show_active (shows Active and Done)
#   The layout of this is not the cleanest in the world just yet.
#   It's just being handled by an if/elif to make separate dicts
#   for each type of Job State and then outputting data from each
#   dict. It should really try to determine a precidence to show
#   only the most recent Job State for a given jobid.
#   Maybe delete jobid from other dicts if it exists in done_master?
#   Changed output so that the header is a separate module.
# 2003-12-03:   DWR
#   Changed end time commandline entry to include end date
#   It was taking the date as dd/mmm/yyyy and assuming 00:00:00
#   for the time, which does NOT include the data from that day.
# 2003-10-30:   DWR
#   Discovered what job type 5 is: Import
#   Discovered what job type 3 is: Verify
#   Added import and verify categories
# 2003-10-28:   DWR
#   Added --mdy switch to readability output so that the interim
#   reporting solution can continue to function. The default format
#   for dates is dd/mmm/yyyy, and this allows for usage of dd/mm/yyyy
# 2003-10-21:   DWR
#   Added readability data handling to individual try information
#   Changed line processing to use the csv module in python 2.3
#   instead of the messy logic to walk the line looking for special
#   cases that broke because of embedded and escaped commas. Because
#   of this, the script now REQUIRES python 2.3
# 2003-10-02:   DWR
#   Started adding Job types for Netbackup 4.5, still need types
#   3 and 5
# 2003-09-17:   DWR
#   Cleaned up logic to find escaped commas in text so that the
#   fields will parse correctly. Known sections where this applies
#   are; path_last_written, filelist, and trystatusdetails.
# 2003-09-16:   DWR
#   Added more debug code for -d switch. This is almost completely
#   for my benefit only to aid in fixing other problems with the
#   script itself. Users would generally not be using it from day
#   to day. Problem lines will generate ERROR: line messages to
#   stderr nw instead of generating a traceback. Most of this exception
#   handling is wrapped around the process_line module since that is
#   where the bulk of the problems would occur.
# 2003-08-11:   DWR
#   Added readability module to the all_data output so human
#   readable output is now possible (-a -v).
# 2003-08-08:   DWR
#   Fixed bug where embedded commas in path last written field
#   would screw up field splitting. Also started to add debug
#   mode switch to get more info that can be collected on stderr

import os
import re
import csv
import sys
import time
import types
import getopt
import string
import cPickle
import fileinput
import traceback

#############################################################################

# definitions for indexed job columns
job_type  = {   '0' : 'Backup',
                '1' : 'Archive',
                '2' : 'Restore',
                '3' : 'Verify',
                '4' : 'Duplicate',
                '5' : 'Import',
                '6' : 'DB Backup',
                '7' : 'Vault'
            }
job_state = { '0' : 'Queued', '1' : 'Active', '2' : 'Re-Queued', '3' : 'Done' }
sched_type = { '0': 'Full', '1' : 'Differential', '2' : 'User Backup', '3' : 'User Archive', '4' : 'Cumulative' }
sub_type = {'0': 'Immediate', '1': 'Scheduled', '2': 'User-Initiated' }
retention_units = { '0': 'Unknown', '1': 'Days', '2': 'Unknown' }

#############################################################################

def usage():
    print >>sys.stderr, '''\nbpdbreport.py usage:

    bpdbreport.py [switches] <filelist> | -

    -a                       all data format (includes try information)
    -d                       run in debug mode (outputs to stderr)
    -f format_file           column output format file
    -s dd/mmm/yyyy           define start time (default is epoch)
    -e dd/mmm/yyyy           define end time (default is current localtime)
    -h                       print this help and exit
    --hoursago hours         sets start time to number of hours ago
                               --hoursago and -s/-e should be mutually
                               exclusive, but they aren't yet. Use only
                               one or the other.
    --mdy                    change verbose date output format to mm/dd/yyyy
    --ymd                    change verbose date output format to yyyy/mm/dd
    --shelve_dicts filename  output dictonary to a python pickle object
                               This option implies -q
    --show_active            show Done and Active jobs
                               (may show duplicates if multiple files are used)
    --show_all               show All jobs
                               (may show duplicates if multiple files are used)
    --show_backups           shows only backup jobs
    --no_header              Omits the header line (useful for further scripting)
    -q                       quiet (no output to stdout)
    --usage                  print detailed help message and exit
    -v                       verbose (human readable output)

    Default output is the first 32 columns from bpdbjobs -report -all_columns
    formatted data. Columns can be defined by format file (see --usage for
    sample format file)

    examples:
        get all entries in verbose format from stdin:
            bpdbreport.py -s 05/may/2003 -e 05/jun/2003 -v -

        get data from file named all_columns.output and display columns defined
        in sample.fmt file
            bpdbreport.py -f sample.fmt all_columns.output

    Lines that generate bad data (mostly because of bugs or bad commas) will
    spit out error lines to stderr in the format of:
        ERROR: inputline
'''

#############################################################################

def detailed_usage():
    usage()
    print >>sys.stderr, '''

# sample format file for column output
# This will skip all lines that start with # and
# all whitespace lines.
# Any lines that are incorrect will be dropped

jobid
jobtype
state
status
class
sched
client
server
start
elapsed
end
stunit
try
operation
kbytes
files
path_last_written
percent
jobpid
owner
subtype
classtype
schedtype
priority
group
master_server
retention_units
retention_period
compression
kbyteslastwritten
fileslastwritten
filelistcount
trypid
trystunit
tryserver
trystarted
tryelapsed
tryended
trystatus
try_status_description
trybyteswritten
tryfileswritten
parentjob
kbpersec
copy
robot
vault
profile
session
ejecttapes
srcstunit
srcserver
srcmedia
dstmedia
stream
suspendable
resumable
restartable
datamovement
frozenimage
backupid
killable
controllinghost'''

#############################################################################

def sec_to_hms( input ):
    input = seconds = int(input)
    hours = seconds / 3600
    seconds = seconds - hours*3600
    minutes = seconds / 60
    seconds = seconds - minutes*60
    return (hours,minutes,seconds)

#############################################################################

def process_line(buffer):
    dict = {}
    idx = 0
    info_labels = ( 'jobid', 'jobtype', 'state', 'status', 'class', 'sched',
                    'client', 'server', 'start', 'elapsed', 'end', 'stunit',
                    'try', 'operation', 'kbytes', 'files', 'path_last_written',#17
                    'percent', 'jobpid', 'owner', 'subtype', 'classtype',
                    'schedtype', 'priority', 'group', 'master_server',
                    'retention_units', 'retention_period', 'compression',
                    'kbyteslastwritten', 'fileslastwritten', 'filelistcount' )
    try_labels1 = ( 'trypid', 'trystunit', 'tryserver', 'trystarted', 'tryelapsed',
                    'tryended', 'trystatus', 'trystatusdescription', 'trystatuscount' )
    try_labels2 = ( 'trybyteswritten','tryfileswritten' )
    info_labels4x = ( 'parentjob', 'kbpersec', 'copy', 'robot', 'vault', 'profile',
                    'session', 'ejecttapes', 'srcstunit', 'srcserver', 'srcmedia',
                    'dstmedia', 'stream' )
    info_labels5x = ( 'suspendable','resumable','restartable','datamovement',
                    'frozenimage','backupid','killable','controllinghost' )

    for label in info_labels:
        dict[label] = buffer[idx]
        idx += 1

    try:
        if dict['filelistcount'] > 0:
            for f in range ( idx, idx+int(dict['filelistcount']) ):
                try:
                    dict['filelist'].append(buffer[idx])
                except:
                    dict['filelist'] = [buffer[idx]]
                idx += 1
        dict['trycount'] = buffer[idx]
        idx += 1

        for job_try in range(1,int(dict['trycount'])+1):
            try_idx = 'try'+str(job_try)
            dict[try_idx] = {}
            for trylabel in try_labels1:
                dict[try_idx][trylabel] = buffer[idx]
                idx += 1
            if dict[try_idx]['trystatuscount'] > 0:
                for f in range ( idx, idx+int(dict[try_idx]['trystatuscount']) ):
                    try:
                        dict[try_idx]['trystatuslines'].append(buffer[idx])
                    except:
                        dict[try_idx]['trystatuslines'] = [buffer[idx]]
                    idx += 1
            for trylabel in try_labels2:
                dict[try_idx][trylabel] = buffer[idx]
                idx += 1
        try:
            for label in info_labels4x:
                dict[label] = buffer[idx]
                idx += 1
        except:
            pass
        try:
            for label in info_labels5x:
                dict[label] = buffer[idx]
                idx += 1
        except:
            pass

        return dict, 0, False
    except:
        return dict, sys.exc_info(),buffer

#############################################################################

def get_output_cols( format_file ):
    try:
        col_fp = open( format_file, 'r' )
    except:
        print >>sys.stderr, 'could not open format file'
        return None

    for line in col_fp:
        line = line.rstrip('\n')
        buf = line.split('#',1)
        if buf[0]:
            try:
                col_fmt.append(buf[0].strip())
            except:
                col_fmt = [buf[0].strip()]
    col_fp.close()
    return col_fmt

#############################################################################

def print_dict(d,k,t):
    if debug_mode:
        print >>sys.stderr,'DEBUG:   ',k,'{'
        keys = d.keys()
        keys.sort()
        for item in keys:
            if type(d[item]) is types.DictType:
                print_dict(d[item],item,t+1)
            elif type(d[item]) is types.ListType:
                print_list(d[item],item,t+1)
            else:
                print >>sys.stderr,'DEBUG:   ','\t'*t+item,':',d[item]
        print >>sys.stderr,'DEBUG:   ','}'
    else:
        print k,'{'
        keys = d.keys()
        keys.sort()
        for item in keys:
            if type(d[item]) is types.DictType:
                print_dict(d[item],item,t+1)
            elif type(d[item]) is types.ListType:
                print_list(d[item],item,t+1)
            else:
                if verbose:
                    print '\t'*t+item,':',readability( item, d[item] )
                else:
                    print '\t'*t+item,':',d[item]
        print '}'

#############################################################################

def print_list(l,k,t):
    if debug_mode:
        idx = 0
        print >>sys.stderr,'DEBUG:   ','\t'*(t-1)+k,'{'
        for item in l:
            if type(item) is types.DictType:
                print_dict(l[idx],item,t+1)
            elif type(item) is types.ListType:
                print_list(l[idx],item,t+1)
            else:
                print >>sys.stderr,'DEBUG:   ','\t'*t+l[idx]
            idx += 1
        print >>sys.stderr,'DEBUG:   ','\t'*(t-1)+'}'
    else:
        idx = 0
        print '\t'*(t-1)+k,'{'
        for item in l:
            if type(item) is types.DictType:
                print_dict(l[idx],item,t+1)
            elif type(item) is types.ListType:
                print_list(l[idx],item,t+1)
            else:
                if verbose:
                    print '\t'*t+readability( item, l[idx] )
                else:
                    print '\t'*t+l[idx]
            idx += 1
        print '\t'*(t-1)+'}'

def output_data( d,col_fmt_input ):
    try_labels1 = ( 'trypid', 'trystunit', 'tryserver', 'trystarted', 'tryelapsed',
                    'tryended', 'trystatus', 'trystatusdescription', 'trystatuscount' )
    try_labels2 = ( 'trybyteswritten','tryfileswritten' )
    list4x = [ 'parentjob', 'kbpersec', 'copy', 'robot', 'vault', 'profile',
            'session', 'ejecttapes', 'srcstunit', 'srcserver', 'srcmedia',
            'dstmedia', 'stream' ]
    list5x = [ 'suspendable','resumable','restartable','datamovement',
            'frozenimage','backupid','killable','controllinghost' ]

    keys = d.keys()
    keys.sort()

    if all_data:
        for key in keys:
            print key,'{'
            k = d[key].keys()
            k.sort()
            for item in k:
                if type(d[key][item]) is types.ListType:
                    print_list(d[key][item],item,1)
                elif type(d[key][item]) is types.DictType:
                    print_dict(d[key][item],item,1)
                else:
                    if verbose:
                        print item,':',readability( item, d[key][item] )
                    else:
                        print item,':',d[key][item]
            print '}*** END',key,'***\n'
        return

    for key in keys:
        col_fmt = col_fmt_input
        nbuVersion = get_nbuVersion(d[key])

        if not col_fmt:
            col_fmt = [ 'jobid', 'jobtype', 'state', 'status', 'class', 'sched',
                    'client', 'server', 'start', 'elapsed', 'end', 'stunit',
                    'try', 'operation', 'kbytes', 'files', 'path_last_written',
                    'percent', 'jobpid', 'owner', 'subtype', 'classtype',
                    'schedtype', 'priority', 'group', 'master_server',
                    'retention_units', 'retention_period', 'compression',
                    'kbyteslastwritten', 'fileslastwritten', 'filelistcount' ]
            if nbuVersion == '4x':
                for item in list4x:
                    col_fmt.append(item)
            elif nbuVersion == '5x':
                for item in list4x:
                    col_fmt.append(item)
                for item in list5x:
                    col_fmt.append(item)

        tries_matter = False
        for h in col_fmt :
            # must ignore the 'try' field...
            if h.startswith('try') and len(h) > 3 :     
                tries_matter = True
                break

        if tries_matter :
            tryline = {}
            try_re = re.compile("^try[0-9][0-9]*")
            for thetry in d[key] :
                if re.match(try_re, thetry) :
                    tryline[thetry] = ''
        else :
            col_out = ''
        for column in col_fmt:
            if column.startswith('try') and column != 'try' :
                try_column = True
            else :
                try_column = False

            #print 'DEBUG', repr(sorted(d[key].keys()))
            #print 'DEBUG', repr(verbose), repr(tries_matter), repr(try_column), column
            if verbose and tries_matter and try_column :
                for the_try in tryline.keys() :
                    data = readability(column, d[key][the_try][column])
                    tryline[the_try] += data+','
            elif verbose and tries_matter and not try_column :
                for the_try in tryline.keys() :
                    data = readability(column, d[key][column])
                    tryline[the_try] += data+','
            elif verbose and not tries_matter and try_column :
                data = readability(column, d[key][column])
                col_out += data+','
            #elif verbose and not tries_matter and not try_column : # case not valid. no tries_matter = no try_col
            elif not verbose and tries_matter and try_column :
                for the_try in tryline.keys() :
                    tryline[the_try] += d[key][the_try][column] + ','
            elif not verbose and tries_matter and not try_column :
                for the_try in tryline.keys() :
                    #print 'DEBUG', repr(d[key]['filelist'])
                    tryline[the_try] += d[key][column] + ','
            #elif not verbose and not tries_matter and try_column : # case not valid. no tries_matter = no try_col
            elif not verbose and not tries_matter and not try_column :
                col_out += d[key][column]+','

#            if verbose and tries_matter :
#                for the_try in tryline.keys() :
#                    data = readability(column, d[key][the_try][column])
#                    tryline[the_try] += data+','
#            elif verbose and not tries_matter :
#                data = readability(column, d[key][column])
#                col_out += data+','
#            elif not verbose and tries_matter :
#                for the_try in tryline.keys() :
#                    print 'DEBUG', repr(d[key][the_try]['POLICY'])
#                    tryline[the_try] += d[key][the_try][column] + ','
#            else :      # not verbose and not tries_matter
#                col_out += d[key][column]+','
        if tries_matter :
            for the_try in sorted(tryline.keys()) :
                col_out = tryline[the_try].rstrip(',')
                print col_out
        else :
            col_out = col_out.rstrip(',')
            print col_out

#############################################################################

def get_nbuVersion(key):
    if key.has_key('suspendable'):
        nbuVersion = '5x'
    elif key.has_key('kbpersec'):
        nbuVersion = '4x'
    else:
        nbuVersion = '3x'
    return nbuVersion

#############################################################################

def print_header( col_fmt,d ):
    ''' This pretty much assumes a 5.1 header for the csv output'''
    if not col_fmt:
        col_fmt = [ 'jobid', 'jobtype', 'state', 'status', 'class', 'sched',
                'client', 'server', 'start', 'elapsed', 'end', 'stunit',
                'try', 'operation', 'kbytes', 'files', 'path_last_written',
                'percent', 'jobpid', 'owner', 'subtype', 'classtype',
                'schedtype', 'priority', 'group', 'master_server',
                'retention_units', 'retention_period', 'compression',
                'kbyteslastwritten', 'fileslastwritten', 'filelistcount',
                'parentjob', 'kbpersec', 'copy', 'robot', 'vault', 'profile',
                'session', 'ejecttapes', 'srcstunit', 'srcserver', 'srcmedia',
                'dstmedia', 'stream', 'suspendable','resumable','restartable',
                'datamovement', 'frozenimage','backupid','killable','controllinghost' ]

    col_out = ''
    for header in col_fmt:
        col_out += header.upper()+','
    col_out = col_out.rstrip(',')
    print col_out

#############################################################################

def readability( key, string ):
    try:
        if key == 'jobtype':
            string = job_type[string]
        elif key == 'state':
            string = job_state[string]
        elif key == 'schedtype':
            string = sched_type[string]
        elif key == 'subtype':
            string = sub_type[string]
        elif key in ['start','end','trystarted','tryended']:
            if mdy:
                string = time.strftime( '%m/%d/%Y %H:%M:%S', time.localtime(int(string)))
            elif ymd:
                string = time.strftime( '%Y/%m/%d %H:%M:%S', time.localtime(int(string)))
            else:
                string = time.strftime( '%d/%b/%Y %H:%M:%S', time.localtime(int(string)))
        elif key in ['elapsed','tryelapsed']:
            (h,m,s) = sec_to_hms(string)
            string = '%d:%02d:%02d' % (h,m,s)
    except:
        pass
    return string

#############################################################################

def output_debug_dict( d ):
    keys = d.keys()
    keys.sort()

    print >>sys.stderr, 'DEBUG:   ', d['jobid'],'{'
    for key in keys:
        if type(d[key]) is types.ListType:
            print_list(d[key],key,1)
        elif type(d[key]) is types.DictType:
            print_dict(d[key],key,1)
        else:
            print >>sys.stderr, 'DEBUG:   ', key,':',d[key]
    print >>sys.stderr, 'DEBUG:   }*** END',d['jobid'],'***'
    return

#############################################################################

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                    "f:s:e:hvxadq", ["hoursago=","shelve_dicts=", "show_active", "show_all", "show_backups", "no_header", "usage", "mdy", "ymd"])
    except getopt.GetoptError, msg:
        # print help information to stderr and exit:
        print "Usage Error:", repr(msg)
        usage()
        sys.exit(2)
    if not args:
        for o, a in opts:
            if o == "-h":
                usage()
                sys.exit()
            if o == "--usage":
                detailed_usage()
                sys.exit()
        print >>sys.stderr, '\nArgument list can not be empty'
        print >>sys.stderr, 'use "-" for stdin'

        usage()
        sys.exit(1)

    # Check to see if filenames are valid files
    argflag = False
    for arg in args:
        if arg != '-':
            if not os.path.exists(arg):
                argflag = True
                print >>sys.stderr, '\nFile', arg, 'does not exist.'
    if argflag:
        usage()
        sys.exit(1)

    # Commandline argument defaults
    all_data        = False                         # -a
    debug_mode      = False                         # -d
    xplicite        = False                         # -x (not used yet)
    verbose         = False                         # -v
    mdy             = False                         # --mdy
    ymd             = False                         # --ymd
    start_date      = 0                             # -s
    show_active     = False                         # --show_active
    show_all        = False                         # --show_all
    show_backups    = False                         # --show_backups
    print_the_header = True                         # --no_header
    end_date        = time.mktime(time.localtime()) # -e
    format_file     = ''                            # -f
    col_fmt         = ''                            # parsed column output string
    shelve_dicts    = False                         # shelve data for future use
    output          = True                          # -q default output, option turns it off

    for o, a in opts:
        if o == "-h":
            usage()
            sys.exit()
        if o == "--usage":
            detailed_usage()
            sys.exit()
        if o == "-f":
            format_file = a
        if o == "-d":
            debug_mode = True
        if o == "--shelve_dicts":
            shelve_dicts = True
            output = False
            pkl = a
        if o == "-q":
            output = False
        if o == "-v":
            verbose = True
        if o == "--show_active":
            show_active = True
        if o == "--show_all":
            show_all = True
            show_active = False
        if o == "--no_header" :
            print_the_header = False
        if o == "--show_backups" :
            show_backups = True
        if o == "--mdy":
            mdy = True
        if o == "--ymd":
            ymd = True
        if o == "--hoursago":
            hoursago = a
            start_date = end_date - int(hoursago) * 3600
        if o == "-s":
            try:
                start_date = time.mktime(time.strptime(a, '%d/%b/%Y'))
            except:
                print >>sys.stderr, '\nDate values must be in dd/mmm/yyyy format'
                usage()
                sys.exit(1)
        if o == "-e":
            try:
                end_date = time.mktime(time.strptime(a, '%d/%b/%Y'))
                end_date += 86399   # Add 23:59:59 to enddate to include that day
            except:
                print >>sys.stderr, '\nDate values must be in dd/mmm/yyyy format'
                usage()
                sys.exit(1)
        if o == "-a":
            all_data = True
        if o == "-x":
            xplicite = True

    done_master = {}
    active_master = {}
    queued_master = {}
    requeued_master = {}

    try:
        if debug_mode:
            print >>sys.stderr, 'DEBUG: Options and Arguments:'
            for o,a in opts:
                print >>sys.stderr, 'DEBUG:   ', o, a
        for inputline in fileinput.input(args):
            try:
                for line in csv.reader([inputline], escapechar='\\'):
                    if show_backups :
                        if line[1] != '0' or line[5] == '-' :
                            # if it's NOT a type=backup ('0') or the schedule IS '-' (aka parent job for
                            # DB's or Exchange), continue
                            continue
                    try:
                        d, exc, buf_debug = process_line(line)
                        if exc:
                            raise
                    except:
                        if debug_mode:
                            print >>sys.stderr, 'DEBUG:  ', '*'*30
                            print >>sys.stderr, 'DEBUG:   Filename:            ', fileinput.filename()
                            print >>sys.stderr, 'DEBUG:   Line Number:         ', fileinput.lineno()
                            print >>sys.stderr, 'DEBUG:   Exception:           ', exc[0]
                            print >>sys.stderr, 'DEBUG:   Exception:           ', exc[1]
                            print >>sys.stderr, 'DEBUG:   Dict Contents:       '
                            output_debug_dict(d)
                            print >>sys.stderr, 'DEBUG:   ', buf_debug
                            print >>sys.stderr, 'DEBUG:   ', line
                            print >>sys.stderr, 'DEBUG:  ', '*'*30
                        else:
                            print >>sys.stderr, 'ERROR: ', line
                    else:
                        try:
                            if int(d['start']) >= start_date and int(d['start']) <= end_date:
                                # To make this cleaner, maybe cross check dicts based on
                                # the assumption that Done jobs are the most important?
                                if int(d['state']) == 0:
                                    if not queued_master.get(d['jobid']):
                                        try:
                                            queued_master[d['jobid']].append(d)
                                        except:
                                            queued_master[d['jobid']] = d
                                elif int(d['state']) == 1:
                                    if not active_master.get(d['jobid']):
                                        try:
                                            active_master[d['jobid']].append(d)
                                        except:
                                            active_master[d['jobid']] = d
                                elif int(d['state']) == 2:
                                    if not requeued_master.get(d['jobid']):
                                        try:
                                            requeued_master[d['jobid']].append(d)
                                        except:
                                            requeued_master[d['jobid']] = d
                                elif int(d['state']) == 3:
                                    if not done_master.get(d['jobid']):
                                        try:
                                            done_master[d['jobid']].append(d)
                                        except:
                                            done_master[d['jobid']] = d
                        except:
                            if debug_mode:
                                exc = sys.exc_info()
                                print >>sys.stderr, 'DEBUG:  ', '*'*30
                                print >>sys.stderr, 'DEBUG:   Filename:            ', fileinput.filename()
                                print >>sys.stderr, 'DEBUG:   Line Number:         ', fileinput.lineno()
                                print >>sys.stderr, 'DEBUG:   Exception:           ', exc[0]
                                print >>sys.stderr, 'DEBUG:   Exception:           ', exc[1]
                                print >>sys.stderr, 'DEBUG:   Dict Contents:       '
                                output_debug_dict(d)
                                print >>sys.stderr, 'DEBUG:   ', buf_debug
                                print >>sys.stderr, 'DEBUG:   ', line
                                print >>sys.stderr, 'DEBUG:  ', '*'*30
                            else:
                                print >>sys.stderr, 'ERROR: ', line
            except:
                print >>sys.stderr, 'ERROR: ', inputline

        if format_file:
            col_fmt = get_output_cols(format_file)
        if output:
            if not all_data:
                if print_the_header :
                    print_header(col_fmt,done_master)
            output_data(done_master, col_fmt)
            if show_active:
                output_data(active_master, col_fmt)
            if show_all:
                output_data(active_master, col_fmt)
                output_data(queued_master, col_fmt)
                output_data(requeued_master, col_fmt)
        if shelve_dicts:
            fp_output = open(pkl, 'wb')
            cPickle.dump(done_master,fp_output,1)
            fp_output.close()

    except KeyboardInterrupt:   # Catch premature ^C
        traceback.print_tb(sys.exc_traceback)
        sys.exit(3)


# modeline vim:set ts=4 sw=4 et:
