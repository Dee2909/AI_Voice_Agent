FROM alpine:3.19

RUN apk add --no-cache \
    asterisk \
    asterisk-speex \
    asterisk-sample-config \
    asterisk-sounds-en \
    asterisk-srtp \
    curl \
    bash

# Copy custom Asterisk configs
COPY telephony/configs/pjsip.conf /etc/asterisk/pjsip.conf
COPY telephony/configs/extensions.conf /etc/asterisk/extensions.conf
COPY telephony/configs/ari.conf /etc/asterisk/ari.conf
COPY telephony/configs/http.conf /etc/asterisk/http.conf
COPY telephony/configs/rtp.conf /etc/asterisk/rtp.conf
COPY telephony/configs/modules.conf /etc/asterisk/modules.conf

EXPOSE 5060/udp 5060/tcp 8088/tcp 10000-10100/udp

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
  CMD /usr/sbin/asterisk -rx "core show sysinfo" || exit 1

CMD ["/usr/sbin/asterisk", "-f", "-vvvddd"]
