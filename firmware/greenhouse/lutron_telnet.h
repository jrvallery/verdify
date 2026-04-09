#pragma once
// lutron_leap.h — Direct ESP32 → Lutron Caseta Pro bridge via LEAP protocol
//
// Uses mutual TLS (client cert) over port 8081.
// Sends JSON GoToLevel commands to control grow light zones.
//
// Bridge: 192.168.10.244:8081 (IoT VLAN, same as ESP32)
// Zones: 86 (Greenhouse Main), 87 (Greenhouse Grow)
// Protocol: LEAP JSON over mutual-TLS TCP

#include "esphome.h"
#include "esp_tls.h"
#include <cstring>
#include <cstdio>

// Embedded certificates (from /mnt/jason/agents/iris/lutron/)
static const char LUTRON_CA_CERT[] = R"EOF(
-----BEGIN CERTIFICATE-----
MIICGTCCAcCgAwIBAgIBATAKBggqhkjOPQQDAjCBgzELMAkGA1UEBhMCVVMxFTAT
BgNVBAgTDFBlbm5zeWx2YW5pYTEUMBIGA1UEBxMLQ29vcGVyc2J1cmcxJTAjBgNV
BAoTHEx1dHJvbiBFbGVjdHJvbmljcyBDby4sIEluYy4xIDAeBgNVBAMTF1NtYXJ0
QnJpZGdlOTA3MDY1QkQ1NTRCMB4XDTE1MTAzMTAwMDAwMFoXDTM1MTAyNjAwMDAw
MFowgYMxCzAJBgNVBAYTAlVTMRUwEwYDVQQIEwxQZW5uc3lsdmFuaWExFDASBgNV
BAcTC0Nvb3BlcnNidXJnMSUwIwYDVQQKExxMdXRyb24gRWxlY3Ryb25pY3MgQ28u
LCBJbmMuMSAwHgYDVQQDExdTbWFydEJyaWRnZTkwNzA2NUJENTU0QjBZMBMGByqG
SM49AgEGCCqGSM49AwEHA0IABLcUYDCIo7mZtDj7cgLW4CrU1U/XNXskc9G2I2+M
YlhhaJJWIXJs9DuZh5AC+Ief6Mw/Vbl3zZX/9bllDigK4LKjIzAhMA4GA1UdDwEB
/wQEAwIBvjAPBgNVHRMBAf8EBTADAQH/MAoGCCqGSM49BAMCA0cAMEQCIHikLd2T
bpN7sz14MRfzLnmlha7JuPXAjYzba00+doa9AiAbOBx3+BdfLpiVUEe9pNZBrhgs
vu0On7ht0yzxB3GjqQ==
-----END CERTIFICATE-----
)EOF";

static const char LUTRON_CLIENT_CERT[] = R"EOF(
-----BEGIN CERTIFICATE-----
MIIC1TCCAnygAwIBAgIBATAKBggqhkjOPQQDAjCBgzELMAkGA1UEBhMCVVMxFTAT
BgNVBAgTDFBlbm5zeWx2YW5pYTEUMBIGA1UEBxMLQ29vcGVyc2J1cmcxJTAjBgNV
BAoTHEx1dHJvbiBFbGVjdHJvbmljcyBDby4sIEluYy4xIDAeBgNVBAMTF1NtYXJ0
QnJpZGdlOTA3MDY1QkQ1NTRCMB4XDTE1MTAzMTAwMDAwMFoXDTM1MTAyNjAwMDAw
MFowWTEYMBYGA1UEAwwPcHlsdXRyb25fY2FzZXRhMRwwGgYKKwYBBAGCuQkBAhMM
MDAwMDAwMDAwMDAwMR8wHQYKKwYBBAGCuQkBAwwPcHlsdXRyb25fY2FzZXRhMIIB
IjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyHqOTHAAX5wuSv+oh5nXOM8Y
xiRMSbu4+hMGgUGsCHTA9Y+EhgNH2yWeBvjjLtxMd6ewIiuUXKidmtW4m4hxz6jY
ifyQtjoDlLQ1kkVMTajfC4Mj5cqTQYUIJxzFFBlY6k3cA21DfX3EayN9pge66NKY
g889kOUaNzucD5n1OHu/oVm5I7be3t34LGzy4o4wYla3MdZ8tCHXbMCEKMgDjtYy
vZJP/RDJDL3ZJALENCY1x+zb3pX1rdMSgTVBWGE2TeXNT3uhcQe49VDJDb/TO22G
IdRoI9FHU4a65tnJ2wkg+EW1+9tPQcyczxGlC1NheD4cWbur+YwypfccB5/iYwID
AQABoz8wPTAOBgNVHQ8BAf8EBAMCBaAwHQYDVR0lBBYwFAYIKwYBBQUHAwEGCCsG
AQUFBwMCMAwGA1UdEwEB/wQCMAAwCgYIKoZIzj0EAwIDRwAwRAIgb80HsoCYZmmK
2o6sTMiSsMzU0DXGIbamEo+z3FfmpqcCID75ZxcPM6fZvxhdEf/LxL4cswDN9b2S
Z+2jHX55++78
-----END CERTIFICATE-----
)EOF";

static const char LUTRON_CLIENT_KEY[] = R"EOF(
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDIeo5McABfnC5K
/6iHmdc4zxjGJExJu7j6EwaBQawIdMD1j4SGA0fbJZ4G+OMu3Ex3p7AiK5RcqJ2a
1bibiHHPqNiJ/JC2OgOUtDWSRUxNqN8LgyPlypNBhQgnHMUUGVjqTdwDbUN9fcRr
I32mB7ro0piDzz2Q5Ro3O5wPmfU4e7+hWbkjtt7e3fgsbPLijjBiVrcx1ny0Idds
wIQoyAOO1jK9kk/9EMkMvdkkAsQ0JjXH7NvelfWt0xKBNUFYYTZN5c1Pe6FxB7j1
UMkNv9M7bYYh1Ggj0UdThrrm2cnbCSD4RbX7209BzJzPEaULU2F4PhxZu6v5jDKl
9xwHn+JjAgMBAAECggEAH8QOO3MHwXPi1e66inny40UqshgFn9fx5cC7/XZ6xtWR
JEJlskJffAxIL5H3lXDstjeeLgaPueWHINs6fCfbjhbn8L1R72iJMWJ4lpZfvR0Z
R8leF8bIcc+dd20UloG0WAlBklLEKI8+tJHpZ98TsQPQN2/QBonMD0e6YQfOa5t6
7CKldKmDJ1AxIDpdr5ZF6IadLrjMfjxNmgRy4c4zSsjI5pqyABRcPTxw3NpSqIl6
hITbxD/kmgsNW1003rKhn+nDmLeVloMdQvcqyNxGHvmFOcBhS68e1Qxokxa1FT7m
CH465KH7xJJVqfjkes0q2xA44wQGLelTJ1ofxBn38QKBgQDrpe6DXRhau2L0r8Fs
UdTI/IDbsC5ePl3G+VusfOyD3y5DdSrp9zeO1QQgSnyPK2Gb2k+QjMS4Tpnl2ip7
S0DaRASuIDSRUvGQVEofiE7V5gkv+4jnqw/nEBHts3jAhFP3U2v2kjPnTToXFST9
eZQT2Z4ETHRIvFoGAEeJ41K2SQKBgQDZywt0DHod/bZqVc42v/WgQnqgKvRKO9y0
UP6DJ/0yRPdZJckIQif55IwrhIz3Pfb5JxhHUr8AIv1EZA42BGUwi9zPvg1kqCf/
C+RxQ3YoqqQXWlibi/t4I7CNWLyy03EQxr3GJW9rJYFNBq/Xk0jQsP9vSHaql985
q/UH0bSjSwKBgQCx+j8spDFyxbi1idES2LNXoa5JPsWmlIALeeZNXoTcDMJKXMIu
t3MUw7o8EUYGdANizP3u9QLXGTaPLbmMKYgv0dOfF9/cKsMb+S2Kp06zquwhe18p
aj+2iqKf3z9CWC96y1zte/sLpX5MVMH9V8gJPgFkycHB9dAgXDGr6S9dUQKBgDue
TWBTGgqjrQ+mtXBfU8mu6Qp3N7AqetwRX9pfU/wyzNLmeQV9tpu9aHFxM3VqzPSf
MxIzIH3VFidmjE1VHq4PWz6y88+eCHTUuJAYu3ueWpTZ8m+B/jCA9I98vwrkvoqt
HL3k+X8HIUIIlpIYi1I1YXcBCxrfwAd1fvnI+f3JAoGAaD4B5X6I9IO0np0IXCsd
9GAUEJVfCOKQqUX4drPUbGkVT5V3hbdS6ga+hiPpGAhRbHl1xOIoHOjKl3uvXFY0
nCckMJw52KTUweEhyaL+qEQKiMc/vPxt2MqJcPqoD6CN0FA7fOHrwpIwVT63Xfr2
tOW3fVPNicdno8U8S1JX4hg=
-----END PRIVATE KEY-----
)EOF";

#define LUTRON_HOST "192.168.10.244"
#define LUTRON_PORT 8081
#define LUTRON_MAIN_ZONE 86
#define LUTRON_GROW_ZONE 87

static const char* TAG_LUTRON = "lutron";
static esp_tls_t *_lutron_tls = NULL;

static void _lutron_close() {
    if (_lutron_tls) {
        esp_tls_conn_destroy(_lutron_tls);
        _lutron_tls = NULL;
    }
}

static bool _lutron_drain_initial() {
    // After TLS connect, bridge sends 2 auto-subscribe responses. Read and discard.
    char buf[1024];
    int total_read = 0;
    uint32_t start = millis();
    while (millis() - start < 2000 && total_read < 800) {
        int n = esp_tls_conn_read(_lutron_tls, (unsigned char*)buf + total_read, sizeof(buf) - total_read - 1);
        if (n > 0) {
            total_read += n;
        } else if (n == 0 || n == ESP_TLS_ERR_SSL_WANT_READ) {
            vTaskDelay(pdMS_TO_TICKS(100));
        } else {
            break;
        }
    }
    if (total_read > 0) {
        buf[total_read] = '\0';
        ESP_LOGD(TAG_LUTRON, "Drained %d bytes of initial bridge messages", total_read);
    }
    return true;
}

static bool lutron_connect() {
    if (_lutron_tls) return true;

    esp_tls_cfg_t cfg = {};
    cfg.cacert_buf = (const unsigned char*)LUTRON_CA_CERT;
    cfg.cacert_bytes = strlen(LUTRON_CA_CERT) + 1;
    cfg.clientcert_buf = (const unsigned char*)LUTRON_CLIENT_CERT;
    cfg.clientcert_bytes = strlen(LUTRON_CLIENT_CERT) + 1;
    cfg.clientkey_buf = (const unsigned char*)LUTRON_CLIENT_KEY;
    cfg.clientkey_bytes = strlen(LUTRON_CLIENT_KEY) + 1;
    cfg.timeout_ms = 5000;
    cfg.non_block = false;

    _lutron_tls = esp_tls_init();
    if (!_lutron_tls) {
        ESP_LOGE(TAG_LUTRON, "esp_tls_init failed");
        return false;
    }

    int ret = esp_tls_conn_new_sync(LUTRON_HOST, strlen(LUTRON_HOST), LUTRON_PORT, &cfg, _lutron_tls);
    if (ret != 1) {
        ESP_LOGE(TAG_LUTRON, "TLS connect to %s:%d failed (ret=%d)", LUTRON_HOST, LUTRON_PORT, ret);
        _lutron_close();
        return false;
    }

    ESP_LOGI(TAG_LUTRON, "TLS connected to Lutron bridge at %s:%d", LUTRON_HOST, LUTRON_PORT);
    _lutron_drain_initial();
    return true;
}

static void lutron_set_zone(int zone, int level) {
    if (!lutron_connect()) {
        ESP_LOGE(TAG_LUTRON, "Cannot connect to Lutron bridge");
        return;
    }

    // Build LEAP JSON command
    char cmd[256];
    snprintf(cmd, sizeof(cmd),
        "{\"CommuniqueType\":\"CreateRequest\",\"Header\":{\"Url\":\"/zone/%d/commandprocessor\"},"
        "\"Body\":{\"Command\":{\"CommandType\":\"GoToLevel\",\"Parameter\":[{\"Type\":\"Level\",\"Value\":%d}]}}}\n",
        zone, level);

    int written = esp_tls_conn_write(_lutron_tls, (const unsigned char*)cmd, strlen(cmd));
    if (written < 0) {
        ESP_LOGW(TAG_LUTRON, "Write failed, reconnecting...");
        _lutron_close();
        if (lutron_connect()) {
            written = esp_tls_conn_write(_lutron_tls, (const unsigned char*)cmd, strlen(cmd));
        }
    }

    if (written > 0) {
        ESP_LOGI(TAG_LUTRON, "LEAP: zone %d → level %d (%s)", zone, level, level > 0 ? "ON" : "OFF");

        // Read response (non-blocking, best effort)
        char resp[512];
        vTaskDelay(pdMS_TO_TICKS(500));
        int n = esp_tls_conn_read(_lutron_tls, (unsigned char*)resp, sizeof(resp) - 1);
        if (n > 0) {
            resp[n] = '\0';
            if (strstr(resp, "201 Created") || strstr(resp, "200 OK")) {
                ESP_LOGI(TAG_LUTRON, "Zone %d confirmed %s", zone, level > 0 ? "ON" : "OFF");
            } else {
                ESP_LOGW(TAG_LUTRON, "Unexpected response: %.100s", resp);
            }
        }
    } else {
        ESP_LOGE(TAG_LUTRON, "Failed to send LEAP command after retry");
    }
}
