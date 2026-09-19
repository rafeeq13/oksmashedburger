#!/bin/bash
ROOT=/var/www/oksmashedburger
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  [[ "$rel" == tools/* ]] && continue
  if [ ! -f "$ROOT/$rel" ]; then
    echo "MISSING $rel"
  fi
done < /tmp/deploy_file_list.txt
echo "VERIFY_DONE"
