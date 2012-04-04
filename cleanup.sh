#!/bin/bash

if [ -f $1 ]; then
    /bin/sed -e 's/01mo-//g' -e 's/03-m0-//g' -e 's/dows//g' \
             -e 's/.atl.weather.com//g' -e 's/.corp.weather.com//g' \
             -e 's/.itdev.weather.com//g' -e 's/ittech.weather.com//g' \
             -e 's/.be.weather.com//g' -e 's/.dmz.weather.com//g' \
             -e 's/erential//g' -e 's/ulative//g' $1 > $2
fi
