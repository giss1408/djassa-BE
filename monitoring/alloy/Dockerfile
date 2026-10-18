# Grafana Alloy with Fidelia's scrape config baked in (config.alloy).
FROM grafana/alloy:v1.10.0
COPY config.alloy /etc/alloy/config.alloy
# The UI and API listen on the private network only (a Render private service).
CMD ["run", "--server.http.listen-addr=0.0.0.0:12345", "--storage.path=/var/lib/alloy/data", "/etc/alloy/config.alloy"]
