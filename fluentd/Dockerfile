FROM fluent/fluentd:v1.16-1

USER root

RUN apk add --no-cache --update --virtual .build-deps \
        build-base ruby-dev \
    && gem install elasticsearch -v 7.17.10 \
    && gem install fluent-plugin-elasticsearch -v 5.3.0 --no-document \
    && gem sources --clear-all \
    && apk del .build-deps \
    && rm -rf /tmp/* /var/tmp/* /usr/lib/ruby/gems/*/cache/*.gem

USER fluent