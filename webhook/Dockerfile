FROM alpine:3.20
RUN apk add --no-cache webhook docker-cli docker-cli-compose curl util-linux bash coreutils
COPY hooks.json /etc/webhook/hooks.json
COPY deploy.sh /usr/local/bin/deploy.sh
RUN chmod +x /usr/local/bin/deploy.sh
EXPOSE 9000
CMD ["webhook", "-hooks", "/etc/webhook/hooks.json", "-template", "-port", "9000", "-verbose"]
