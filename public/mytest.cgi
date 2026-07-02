#!/bin/bash

# 1. Mandatory HTTP Header followed by an empty line
echo "Content-Type: text/plain"
echo ""

# 2. Read the environment variable and print the body
echo "Success! The server received the following QUERY_STRING:"
echo "$QUERY_STRING"
