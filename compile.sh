#!/usr/bin/env bash

output="result.md"
> "$output"

for problem in problem1 problem2 problem3 problem4; do
  echo "* $problem" >> "$output"

  # get unique model prefixes
  ls *${problem}*.json 2>/dev/null | \
  sed -E "s/_${problem}_run[0-9]+\.json//" | sort -u | while read model; do

    echo "  * $model" >> "$output"

    # iterate runs
    ls ${model}_${problem}_run*.json 2>/dev/null | sort | while read file; do
      run=$(echo "$file" | grep -o 'run[0-9]\+')
      echo "    * $run" >> "$output"

      echo "" >> "$output"
      echo '```' >> "$output"
      jq -r '.content // "[EMPTY]"' "$file" >> "$output"
      echo '```' >> "$output"
      echo "" >> "$output"
    done
  done

  echo "" >> "$output"
done
