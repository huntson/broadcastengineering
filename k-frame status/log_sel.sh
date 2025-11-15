#!/bin/sh

FatalCheck=""
AlertCheck=""
ErrorCheck=""
WarningCheck=""
InfoCheck=""

FatalGo=""
AlertGo=""
ErrorGo=""
WarningGo=""
InfoGo=""

StartupCheck=""
HWDriverCheck=""
KFDCheck=""
MFDCheck=""
NetworkIOCheck=""
UCPPCheck=""
OnlineCommCheck=""
ConfigurationCheck=""
SNMPAlarmCheck=""
CPL_TxCheck=""
CPL_RxCheck=""

LoggingFolder="../../../var/log/"
LoggingFile=""
Lfile=""
button=0

local query entry key value button

query="${QUERY_STRING}&"			#put an extra "&" on the end for boundary case parsing.

# parse the query data
while [ ! -z "$query" ];
do
	entry="${query%%&*}"  		# get first part of query string
	key="${entry%%=*}"  		# get the key (variable name) from it
	value="${entry#*=}"   		# get the value from it
	query="${query#$entry&*}"	# strip first part from query string
		
	case "$key" in
		FatalLevel) FatalGo="-e $value"
			FatalCheck="CHECKED";;
		AlertLevel) AlertGo="-e $value"
			AlertCheck="CHECKED";;
		ErrorLevel) ErrorGo="-e $value"
			ErrorCheck="CHECKED";;
		WarningLevel) WarningGo="-e $value"
			WarningCheck="CHECKED";;
		InfoLevel) InfoGo="-e $value"
			InfoCheck="CHECKED";;
		LogFile) LoggingFile="$value";;
		Submit) button="$value";;
	esac

	case "$value" in
		Prev) button="$key";;
		Next) button="$key";;
		Reload) button="$key";;
		Create+PanelSWDiag) button="$key";;
		View) button=0;;
	esac
done

case "$LoggingFile" in
	"Startup.log") StartupCheck="CHECKED";;
	"HWDriver.log") HWDriverCheck="CHECKED";;
	"Kayenne_Frame_Driver.log") KFDCheck="CHECKED";;
	"MainFrameDriverSystem.log") MFDCheck="CHECKED";;
	"NetworkIO.log") NetworkIOCheck="CHECKED";;
	"UCPP.log") UCPPCheck="CHECKED";;
	"OnlineComm.log") OnlineCommCheck="CHECKED";;
	"Configuration.log") ConfigurationCheck="CHECKED";;
	"SNMPAlarm.log") SNMPAlarmCheck="CHECKED";;
	"CPL_Tx.log") CPL_TxCheck="CHECKED";;
	"CPL_Rx.log") CPL_RxCheck="CHECKED";;
esac

echo "Content-type: text/html"
echo ""
echo "<html>"

echo "<head>"
echo "<link href=\"../include/styles.css\" rel=\"stylesheet\" type=\"text/css\" />"
echo "<script>"
echo "function scrollToBottom() {"
echo "    window.scrollTo(0, document.body.scrollHeight);"
echo "}"
echo "function reloadAndScroll() {"
echo "    window.location.reload(); // Reload the page"
echo "}"
echo "window.onload = function() {"
echo "    scrollToBottom(); // Scroll to bottom when the page loads initially"
echo "    setTimeout(reloadAndScroll, 30000); // Reload the page after 30 seconds"
echo "    setTimeout(scrollToBottom, 500); // Scroll to bottom after 1 second"
echo "}"
echo "</script>"
echo "</head>"

# Config info in body
echo "<body>"
echo "<form action=\"./log_selection.sh\">"

#echo "<p class=\"page_note\">\"$QUERY_STRING\"</p>"
#echo "<p class=\"page_note\">\"$button\"</p>"

local savedSWDiag="0"
local fileName="panelSWDiag.tgz"
local relativePathFromFlash3="../flash/www/documents"
if [ $button == "CreatePanelSWDiag" ]; then
   # need to run the tar script from the location they exist. The relative file paths are remembered.
   # also the gzip works but the resultant file does not seem work with winzip
   `cd ../../../flash3 ; ./tarSWDiag.sh $relativePathFromFlash3 $fileName`
   local filePath="../documents/"$fileName
   # echo "<p class=\"page_note\">$filePath</p>"
   if [ -f $filePath ]; then
      savedSWDiag="1"
      #echo "<p class=\"page_note\">found $fileName</p>"
   fi

fi

echo "<table>"
     # Logging
     echo "<tr>"
     echo "<td class=\"page_title\">Logging</td>"
     echo "</tr>"

     # Log Level Selection
     echo "<tr>"
     echo "<td class=\"table_header\">Log Level Selection</td>"
     echo "</tr>"
echo "</table>"

echo "<table>"
     # Message levels
     echo "<tr colspan=3>"
          echo "<td class=\"table_label_left\"><input type=\"checkbox\" name=\"ErrorLevel\" id=\"Error\" value=\"ERROR\" "$ErrorCheck" />Error</td>"
          echo "<td class=\"table_label_left\"><input type=\"checkbox\" name=\"WarningLevel\" id=\"Warning\" value=\"WARN\" "$WarningCheck" />Warning</td>"
          echo "<td class=\"table_label_left\"><input type=\"checkbox\" name=\"InfoLevel\" id=\"Info\" value=\"INFO\" "$InfoCheck" />Info</td>"
     echo "</tr>"
     echo "<tr>"
          echo "<td class=\"table_label_left\"><input type=\"checkbox\" name=\"FatalLevel\" id=\"Fatal\" value=\"FATAL\" "$FatalCheck" />Fatal</td>"
          echo "<td class=\"table_label_left\"><input type=\"checkbox\" name=\"AlertLevel\" id=\"Alert\" value=\"ALERT\" "$AlertCheck" />Alert</td>"
     echo "</tr>"
echo "</table>"

echo "<table>"
     # Log File Category
     echo "<tr>"
          echo "<td class=\"table_header\">Log File Category</td>"
     echo "</tr>"
echo "</table>"

echo "<table>"
     # Log File Category
     echo "<tr colspan=4>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"Startup.log\" "$StartupCheck" />Startup</td>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"HWDriver.log\" "$HWDriverCheck" />HW Driver</td>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"Kayenne_Frame_Driver.log\" "$KFDCheck" />Kayenne Frame Driver</td>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"MainFrameDriverSystem.log\" "$MFDCheck" />Mainframe Driver System</td>"
     echo "</tr>"
     echo "<tr>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"NetworkIO.log\" "$NetworkIOCheck" />Network IO</td>"
          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"UCPP.log\" "$UCPPCheck" />UCPP</td>"
#          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"OnlineComm.log\" "$OnlineCommCheck" />Online Comm</td>"
#          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"Configuration.log\" "$ConfigurationCheck" />Configuration</td>"
     echo "</tr>"
#     echo "<tr>"
#          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"SNMPAlarm.log\" "$SNMPAlarmCheck" />SNMP Alarm</td>"
#          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"CPL_Tx.log\" "$CPL_TxCheck" />CPL Tx</td>"
#          echo "<td class=\"table_label_left\"><input type=\"radio\" name=\"LogFile\" value=\"CPL_Rx.log\" "$CPL_RxCheck" />CPL Rx</td>"
#     echo "</tr>"
echo "</table>"

echo "<br>"

echo "<table><tr><td><input type=\"submit\" name=\"0\" value=\"View\" /></td>"
if [ "$savedSWDiag" -eq "1" ]; then
    echo "<td><input type=\"submit\" name=\"CreatePanelSWDiag\" value=\"Create PanelSWDiag\" /></td>"
    echo "<td><input type=\"button\" value=\"Save to a local drive\" onClick=\"window.location.href='/documents/$fileName'\"></td>"
else
    echo "<td><input type=\"submit\" name=\"CreatePanelSWDiag\" value=\"Create PanelSWDiag\" /></td>"
fi
echo "</tr></table>"

i=$button
j=`expr $i + 1`
h=`expr $i - 1`

#echo "j="$j"<br>"
#echo "h="$h"<br>"
#echo "LoggingFile="$LoggingFile"<br>"

Lfile="${LoggingFile}.$i"

echo "<table>"
     echo "<tr>"
     echo "<td class=\"table_header_small\">"
     if [ -f "../../../var/log/"$Lfile ]; then
	        echo $Lfile
	        echo "</td>"
     else
         echo $LoggingFile
         echo "</td>"
         Lfile=$LoggingFile
         echo "<td class=\"bad_table_value\">"
         if [ $LoggingFile != "" ]; then
            if [ -f "../../../var/log/"$Lfile ]; then :; else
               echo "Not Found"
            fi
         fi
         echo "</td>"
     fi
     echo "</td>"
     echo "</tr>"
echo "</table>"

echo "<table>"
     echo "<tr colspan=3>"
     echo "<td>"
     if [ $LoggingFile != "" ]; then
        if [ -f "../../../var/log/"$Lfile ]; then
           echo "<input type=\"submit\" name=\""$i"\" value=\"Reload\" />"
	     fi
      fi
      echo "</td>"
      echo "<td width=\"45\">"
      if [ -f "../../../var/log/"$LoggingFile"."$j ]; then
         echo "<input type=\"submit\" name=\""$j"\" value=\"Prev\" />"
      fi
      echo "</td>"
      echo "<td>"
      if [ -f "../../../var/log/"$LoggingFile"."$h ]; then
         echo "<input type=\"submit\" name=\""$h"\" value=\"Next\" />"
      else
          if [ $LoggingFile != "" ]; then
             if [ $LoggingFile != $Lfile ]; then
		          echo "<input type=\"submit\" name=\"0\" value=\"Next\" />"
            fi
          fi
      fi
      echo "</td>"
      echo "</tr>"
echo "</table>"

echo "</form>"

if [ -f "../../../var/log/"$Lfile ]; then
   echo "<table>"
        echo "<tr>"
        echo "<td class=\"table_light\">"
	     if [ `grep -c $FatalGo $AlertGo $ErrorGo $WarningGo $InfoGo ../../../var/log/$Lfile` -eq 0 ]; then
	        echo "No Level matches in the selected file."
	     else
	         echo "<pre>"
	         echo `grep $FatalGo $AlertGo $ErrorGo $WarningGo $InfoGo ../../../var/log/$Lfile | awk '/FATAL || ALERT || WARN || ERROR || INFO/ { ORS = "<BR>" ; print $0 }'`
	         echo "</pre>"
        fi
        echo "</td>"
	     echo "</tr>"
   echo "</table>"
fi

echo "<br>"

# Prints whatever was entered in the form:
#echo "$QUERY_STRING"|awk -F'&' '{for(i=1;i<=NF;i++){print $i;print"<br />"}}'
echo "<p>Last reload time: $(date +"%Y-%m-%d %H:%M:%S")</p>"

echo "</body>"

echo "</html>"
