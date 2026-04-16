# bash script to continuously convert/transfer video files off RPi
# converts .h264 files to .mp4 using framerate saved in filename
# copies converted files (and associated events and frames files) into folders based on date
# performs MD5 checksum
# checks for new files every night at midnight

RCPATH=/mnt/videoShare # mounted folder
FileSearch=*.frames
transferTime="06:05"

# loop continuously
while true; do

    count=`ls -1 $FileSearch 2>/dev/null | wc -l`
    if [ $count != 0 ]; then

        # for each .frames file
        for fname in $FileSearch; do

            # if h264 file exists, convert it
            ext1=".h264"
            ext2=".mp4"
            f_h264=${fname%%.*}$ext1
            f_mp4=${fname%%.*}$ext2

            attempts=0
            while [ -e $f_h264 ] && [ ! -e $f_mp4 ]; do
                FPS=${fname:1:2}
                MP4Box -fps $FPS -new -add $f_h264 $f_mp4
                sleep 0.2
                attempts=attempts+1
            done
            # remove h264 after successful conversion
            if [ -e $f_mp4 ]; then
                rm $f_h264
            fi

            # extract time/date
            moddate=$(date --reference=$fname +%Y%m%d)
            modtime=$(date --reference=$fname +%H)
            # for videos that are modified after midnight
            if [ $modtime -eq 0 ] && [ ${fname:4:5} -gt 86000 ];  then
                # subtract a day
                moddate=$(date --date="${moddate} -1 day" +%Y%m%d)
            fi
            if [ ! -d "$RCPATH/$moddate" ]; then
                mkdir $RCPATH/$moddate
            fi

            # check for all three files (esp mp4)
            count2=`ls -1 ${fname%%.*}* 2>/dev/null | wc -l`
            if [ $count2 -eq 3 ] && [ -e $f_mp4 ]; then
                # copy all related files
                for fcopy in ${fname%%.*}*; do
                    copied=false
                    attempts=0
                    echo "File: $fcopy"
                    while [ "$copied" = false ]; do
                        MD5_BEFORE="$(md5sum < $fcopy)"
                        MD5_BEFORE="${MD5_BEFORE::-3}"
                        #echo "${MD5_BEFORE}"

                        cp $fcopy $RCPATH/$moddate
                        #sleep $((attempts+1))

                        file=$RCPATH/$moddate/$fcopy

                        if [ ! -f "$file" ]; then
                            attempts=$((attempts+1))
                            echo "file $fcopy was not transferred successfully after $attempts attempts."
                            sleep 1
                        else
                            MD5_AFTER="$(md5sum < $file)"
                            MD5_AFTER="${MD5_AFTER::-3}"
                            #echo "${MD5_AFTER}"

                            if [ "$MD5_AFTER" != "$MD5_BEFORE" ]; then
                                attempts=$((attempts+1))
                                echo "ERROR: KEEP $fcopy. $attempts attempts"
                                rm -f $file
                                sleep 1
                            else
                                echo "SUCCESS: Remove $fcopy"
                                copied=true
                                rm -f $fcopy
                                date +%k:%M:%S
                            fi
                        fi

                    done # end while copied loop
                    echo $''
                done # end for fcopy loop
            fi
        done # end for fname loop
    fi

    count=`ls -1 $FileSearch 2>/dev/null | wc -l`
    if [ $count != 0 ]; then
        echo "No sleeping, more to convert"
    else
        #echo "Sleep for 2 min before next check"
        #sleep 120

        current_epoch=$(date +%s)
        target_epoch=$(date -d "${transferTime} today" +%s)
        if [ $target_epoch -lt $current_epoch ]; then
          target_epoch=$(($target_epoch+86400))
        fi
        sleep_seconds=$(( $target_epoch - $current_epoch ))
        if [ $sleep_seconds -lt 90 ]; then
          sleep_seconds=90
        fi
        echo "Sleep until $transferTime ($sleep_seconds seconds)"
        sleep $sleep_seconds
    fi
done # end while true loop
