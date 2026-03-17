#!/bin/sh
# Download answers and run setup-alpine
wget http://10.0.2.2:8099/answers -O /tmp/answers
ERASE_DISKS=/dev/vda setup-alpine -f /tmp/answers
