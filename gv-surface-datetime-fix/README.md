Fix for Grass Valley Kayenne surface date/time year limit. The stock sysDateTime.sh CGI script rejects any year above 2025, preventing time sync from working in 2026+. This patched version extends the max year to 2036.

Change: Line 72 — `2025` changed to `2036`


To install:

FTP to panel: root/root
Drop script in /flash/www/cgi-bin
CHMOD to 755

Verify at:

http://<ip_address>/cgi-bin/sysDateTime.sh
