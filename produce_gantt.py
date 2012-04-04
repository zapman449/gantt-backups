#!/usr/bin/python

import csv
import os.path
import sys
import time

import CairoPlot

def scaled_times(times, first) :
    """
    Scale times of each job's tries in the form of 
         [(start,end), (start,end) ...]
    to the time of the first job starting.  Translates from reality to 
    CairoPlot relative reality.
    """
    results = []
    for start, end in times :
        delta_0_start = float(start - first)
        delta_0_end = float(end - first)
        # now append the deltas, scaled to hours (hence the 3600) the .0
        # re-enforces the idea that these must be floating point
        results.append( ((delta_0_start / 3600.0), (delta_0_end / 3600.0)))
    return results

def calc_vticks(first, last) :
    """
    Make a list of hour strings from the first job starting to the
    last job ending.
    Imputs:
        first is time in seconds since epoch, of the first job starting
        last is time in seconds since epoch of the last job ending.
    """
    first_hour = time.localtime(first).tm_hour
    delta_hours = ((last - first) // 3600)
    return [ str((h + first_hour) % 24) for h in range(delta_hours + 1) ]

def parse_commandline() :
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]) :
        f = open(sys.argv[1])
    elif len(sys.argv) > 1 :
        USAGE()
        sys.exit(1)
    else :
        f = sys.stdin
    return f


def main() :
    #h_pixals = 1600
    h_pixals = 1360
    # 500 horizontal pixals: 120 for names, 380 for bars.
    #     380 gives 10 nice bars..  I need 16 bars, so 60/bar = 960
    #     120 for names of 7 chars.  I have at least 38 chars. assume 42.
    #          120 * 6 = 720
    #     960 + 640 = 1600 horizontal pixals.
    h_legend = []
    allstarts = []
    allends = []
    colors = []
    tasknames = []
    pieces = []
    bars = {}
    starttimes = {}
    bar_color = (1.0, 0.7, 0.0)

    f = parse_commandline()

    for inputline in f :
        for line in csv.reader([inputline], escapechar='\\'):
            name = "__".join(line[0:3])
            start = int(line[3])
            end = int(line[4])
            #if time.gmtime(end)[3:5] == (6,13) :
            #    print name
            bars.setdefault(name, []).append((start,end))
            allstarts.append(start)
            allends.append(end)
            starttimes.setdefault(start, []).append(name)

    first = min(allstarts)
    last = max(allends)
    v_tickmarks = calc_vticks(first, last)
    v_pixals = (len(bars.keys()) + 1) * 70
    # 350 vertical pixals.  70 for each task + 70 for headers.
    # v_tickmarks = scale_vlines(first, last)
    for start in sorted(starttimes.keys()) :
        for name in starttimes[start] :
            # one task name.
            tasknames.append(name)
            # need 1 color per name
            colors.append(bar_color)
            times = bars[name]
            #print 'debug', name
            pieces.append(scaled_times(times, first))

    CairoPlot.gantt_chart('visual_schedule', pieces, h_pixals, v_pixals, 
                          tasknames, v_tickmarks, colors)

if __name__ == '__main__' :
    main()
