# Environment Variables

Bumper has a number of environment variables to help with custom deployments and configuration.  These should be set prior to executing Bumper.

| Setting            | Value                              | Description                                                                                                                 |
| ------------------ | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| BUMPER_LISTEN      | {ipv4 address}                     | IP address to start server listeners on                                                                                     |
| BUMPER_ANNOUNCE_IP | {ipv4 address}                     | IP address to tell bots when they request the server location.  May need to be set in cases such as when LISTEN is 0.0.0.0. |
| BUMPER_CA          | {full path to ca.crt location}     | The public CA certificate (ca.crt) to be loaded                                                                             |
| BUMPER_CERT        | {full path to bumper.crt location} | The public server certificate (bumper.crt) to be used by the Bumper server                                                  |
| BUMPER_KEY         | {full path to bumper.key location} | The private server key (bumper.key) to be used by the Bumper server                                                         |
| BUMPER_LOGS        | {full path to logs directory}      | The directory where logs should be stored                                                                                   |
| BUMPER_DATA        | {full path to data directory}      | The directory where persistent data should be stored (bumper.db)                                                            |
| BUMPER_DEBUG       | true                               | Run Bumper with debug mode/logging                                                                                          |
| LOG_TO_STDOUT      | true                               | Instead of logging to logs/, logs to to STDOUT |
| BUMPER_TLS_MIN_VERSION | TLSv1 (default), TLSv1_1, TLSv1_2, TLSv1_3 | Lowest TLS version accepted on the HTTPS (443), MQTT (8883) and XMPP STARTTLS (5223) listeners. The default accepts TLS 1.0 like Bumper always did, because older robots may not support anything newer (on OpenSSL 3 this needs security level 0). Set `TLSv1_2` or higher if all your robots support it; Bumper logs the version each TLS connection negotiated. |
| BUMPER_PORT_HTTPS  | {port}, default 443                | Port of the HTTPS config server. Bots and apps always connect to 443, so if you change it (for example to run without root under `network_mode: host`), forward 443 to it. |
| BUMPER_PORT_HTTP   | {port}, default 8007               | Port of the plain-HTTP config server (bots fetch `lookup.do` from it). |
| BUMPER_PORT_MQTT   | {port}, default 8883               | Port of the MQTT broker (TLS). |
| BUMPER_PORT_XMPP   | {port}, default 5223               | Port of the XMPP server. Bots are always told to connect to 5223, so forward 5223 to it if you change it. |

`BUMPER_LOGS` is used for the log files (bumper.log, confserver.log, mqttserver.log, helperbot.log, boterror.log, xmppserver.log) unless `LOG_TO_STDOUT` is set. Note that `LOG_TO_STDOUT` is enabled by *any* non-empty value, including `false`.
