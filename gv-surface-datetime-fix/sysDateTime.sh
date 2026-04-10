#!/bin/sh
echo "Content-type: text/html"
echo ""
echo "<html>"

echo "<head>"
echo "<link href=\"../include/styles.css\" rel=\"stylesheet\" type=\"text/css\" />"
echo "</head>"

# Config info in body
echo "<body>"
echo "<form action=\"./sysDateTime.sh\">"

local query entry key value button valuelength
local currentDay=`date +%d`
local currentMonth=`date +%m`
local currentYear=`date +%C%y`
local currentHour=`date +%H`
local currentMinute=`date +%M`
local currentSecond=`date +%S`

local pageDay="$currentDay"
local pageMonth="$currentMonth"
local pageYear="$currentYear"
local pageHour="$currentHour"
local pageMinute="$currentMinute"
local pageSecond="$currentSecond"

local allValid="true"
local leadingZero="0"

query="${QUERY_STRING}&"			#put an extra "&" on the end for boundary case parsing.

#Debug
#echo "<p class=\"page_note\">\"$query\"</p>"


# parse the query data
while [ ! -z "$query" ];
do
	entry="${query%%&*}"  		# get first part of query string
	key="${entry%%=*}"  		# get the key (variable name) from it
	value="${entry#*=}"   		# get the value from it
	query="${query#$entry&*}"	# strip first part from query string
        valuelength=`expr length "$value"`


	case "$key" in
		Day)
		     if [ "$value" -ge "1" ] && [ "$value" -le "31" ]; then
		        if [ "$valuelength" -eq 1 ]; then
                           pageDay="$leadingZero$value"
                        else
                           pageDay="$value"
                        fi
		     else
		         allValid="false"
		     fi
                     ;;
		Month)
		     if [ "$value" -ge "1" ] && [ "$value" -le "12" ]; then
  		        if [ "$valuelength" -eq 1 ]; then
                           pageMonth="$leadingZero$value"
                        else
                           pageMonth="$value"
                        fi
		     else
		         allValid="false"
		     fi
                     ;;
		Year) pageYear="$value"
		     if [ "$value" -ge "1970" ] && [ "$value" -le "2036" ]; then
		        pageYear="$value"
		     else
		         allValid="false"
		     fi
                     ;;
 		Hour)
		     if [ "$value" -ge "0" ] && [ "$value" -le "23" ]; then
  		        if [ "$valuelength" -eq 1 ]; then
                           pageHour="$leadingZero$value"
                        else
                           pageHour="$value"
                        fi
		     else
		         allValid="false"
		     fi
                     ;;
		Minute)
		     if [ "$value" -ge "0" ] && [ "$value" -le "59" ]; then
   		        if [ "$valuelength" -eq 1 ]; then
                           pageMinute="$leadingZero$value"
                        else
                           pageMinute="$value"
                        fi
		     else
		         allValid="false"
		     fi
                     ;;
		Second) pageSecond="$value"
		     if [ "$value" -ge "0" ] && [ "$value" -le "59" ]; then
    		        if [ "$valuelength" -eq 1 ]; then
                           pageSecond="$leadingZero$value"
                        else
                           pageSecond="$value"
                        fi
		     else
		         allValid="false"
		     fi
                     ;;
		SaveNewSettings) button="SaveNewSettings";;
                Refresh) button="Refresh"
	esac
done

if [ "$button" = "Refresh" ]; then
   pageDay="$currentDay"
   pageMonth="$currentMonth"
   pageYear="$currentYear"
   pageHour="$currentHour"
   pageMinute="$currentMinute"
   pageSecond="$currentSecond"
fi

echo "<table>"
	# System Date & Time
	echo "<tr>"
		echo "<td class=\"page_title\">Panel Date & Time</td>"
	echo "</tr>"
echo "</table>"

echo "<table>"
	# Date
	echo "<tr colspan=3>"
		echo "<td class=\"table_header\">Date</td>"
	echo "</tr>"

	# Day
	echo "<tr>"
		echo "<td class=\"table_label\">Day:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Day\" size=\"4\" value=\"$pageDay\"/></td>"
		echo "<td class=\"table_label_left\">(1 to 31)</td>"
	echo "</tr>"

	# Month
	echo "<tr>"
		echo "<td class=\"table_label\">Month:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Month\" size=\"4\" value=\"$pageMonth\"/></td>"
		echo "<td class=\"table_label_left\">(1 to 12)</td>"
	echo "</tr>"

	# Year
	echo "<tr>"
		echo "<td class=\"table_label\">Year:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Year\" size=\"4\" value=\"$pageYear\"/></td>"
	echo "</tr>"

	# Time
	echo "<tr colspan=3>"
		echo "<td class=\"table_header\">Time</td>"
	echo "</tr>"

	# Hour
	echo "<tr>"
		echo "<td class=\"table_label\">Hour:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Hour\" size=\"4\" value=\"$pageHour\"/></td>"
		echo "<td class=\"table_label_left\">(0 to 23)</td>"
	echo "</tr>"

	# Minute
	echo "<tr>"
		echo "<td class=\"table_label\">Minute:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Minute\" size=\"4\" value=\"$pageMinute\"/></td>"
		echo "<td class=\"table_label_left\">(0 to 59)</td>"
	echo "</tr>"

	# Second
	echo "<tr>"
		echo "<td class=\"table_label\">Second:</td>"
		echo "<td class=\"table_textbox\">"
		echo "<input type=\"text\" name=\"Second\" size=\"4\" value=\"$pageSecond\"/></td>"
		echo "<td class=\"table_label_left\">(0 to 59)</td>"
	echo "</tr>"

echo "</table>"

	echo "<BR>"
	echo "<tr>"
		echo "<input type=\"submit\" name=\"SaveNewSettings\" value=\"Apply\" /></td>"
		echo "<input type=\"submit\" name=\"Refresh\" value=\"Refresh\" /></td>"
	echo "</tr>"

local dot="."
local newDate="$pageMonth$pageDay$pageHour$pageMinute$pageYear$dot$pageSecond"

#echo "<tr><td class=\"table_label\">$newDate</td></tr>"
#echo "<tr><td class=\"table_label\">$allValid</td></tr>"

if [ "$allValid" = "false" ]; then
   echo "<table><BR><tr><td class=\"bad_table_value\">One or more values are not valid. The time has not been set.</td></tr></table>"
elif [ "$button" = "SaveNewSettings" ]; then
    `date -s "$newDate"`
    `hwclock -w`
fi

echo "</form>"

# Prints whatever was entered in the form:
#echo "$QUERY_STRING"|awk -F'&' '{for(i=1;i<=NF;i++){print $i;print"<br />"}}'

echo "</body>"

echo "</html>"
