#!/bin/bash
# Run on server: curl key routes, report non-200
BASE="http://127.0.0.1:8001"
paths="/ /menu /about /catering /careers /news /faq /rewards /gift-cards /deals /locations /contact /login /register /cart /checkout"
fail=0
for p in $paths; do
  code=$(curl -s -o /tmp/r.html -w '%{http_code}' "$BASE$p")
  if [ "$code" != "200" ] && [ "$code" != "302" ] && [ "$code" != "301" ]; then
    echo "FAIL $code $p"
    fail=1
  else
    echo "OK $code $p"
  fi
done
journalctl -u oksmashedburger.service -n 15 --no-pager | grep -E 'TemplateNotFound|Traceback|Error' | tail -5 || true
exit $fail
