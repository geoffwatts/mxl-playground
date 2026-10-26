/* SPDX-License-Identifier: MIT */
#include "management_vlan_requests.h"

static int equal(const char *a, const char *b)
{
    unsigned i;
    if (!a || !b) return 0;
    for (i = 0; i < 128; i++) {
        if (a[i] != b[i]) return 0;
        if (!a[i]) return 1;
    }
    return 0;
}
int mxl_mgmt_request_kind(const char *method, const char *path)
{
    /* Exactly matched paths from this build's audited handlers. No extension,
     * prefix, percent-encoding or HTTP-method assumptions grant admission.
     * Native reads using POST remain blocked until individually admitted.
     */
    static const char *const reads[] = {
        "/", "/setup.html", "/login.html", "/authorize", "/logout.json",
        "/status.json", "/port_setting_load.json", "/port_statistics.json",
        "/network_settings.json", "/port_vlan.json", "/tag_vlan.json",
        "/stp.json", "/port_lock_cfg.json", "/port_loop_status.json",
        "/port_trunk_cfg.json", "/port_trunk_refresh.json", "/port_mirror.json",
        "/mac_get_dynamic_mac_entries.json", "/mac_get_static_mac_entries.json",
        "/igmp_config.json", "/igmp_rp_config.json", "/igmp_query_config.json",
        "/igmp_get_entries.json", "/storm_ctrl_cfg.json", "/eee_config.json",
        "/dhcp_snooping_cfg.json", "/sntp_setting.json", "/systemtime_settings.json",
        "/qos_get_rate_limit.json", "/qos_get_port_mode.json",
        "/qos_get_port_priority.json", "/qos_queue_sched.json",
        "/qos_get_tc_q_map.json", "/qos_get_dscp_tc_map.json", "/qos_get_cos_tc_map.json",
        "/jumbo.json", "/sfp.json", "/inventory.json", "/config/download",
        "/management-vlan-probe.json", "/management-vlan-platform-probe.json",
        "/management-vlan-timer-probe.json", "/management-vlan-ip-hook-probe.json",
        "/management-vlan-egress-probe.json"
    };
    unsigned i;
    /* These POST handlers only read LLDP state or change authentication and
     * identity metadata. They do not alter CPU/VLAN classification. */
    if (equal(method,"POST") &&
        (equal(path,"/logout.json") || equal(path,"/lldp_loadsts.json") ||
         equal(path,"/lldp_fetch_rx_data.json") || equal(path,"/inventory.json") ||
         equal(path,"/set_des.json") || equal(path,"/save_all_configs.json") ||
         equal(path,"/jumbo.json"))) return MXL_MGMT_REQUEST_READ;
    if (equal(path, "/management-vlan.json") &&
        (equal(method, "GET") || equal(method, "POST"))) return MXL_MGMT_REQUEST_CONTROL;
    if (!equal(method, "GET")) return MXL_MGMT_REQUEST_NATIVE;
    for (i = 0; i < sizeof(reads) / sizeof(reads[0]); i++)
        if (equal(path, reads[i])) return MXL_MGMT_REQUEST_READ;
    return MXL_MGMT_REQUEST_NATIVE;
}
int mxl_mgmt_requests_idle(const struct mxl_mgmt_requests *s)
{
    unsigned i, count = 0;
    if (!s || s->fault || s->count > MXL_MGMT_REQUEST_SLOTS) return 0;
    for (i = 0; i < MXL_MGMT_REQUEST_SLOTS; i++) if (s->connection[i]) count++;
    return !count && !s->count;
}
int mxl_mgmt_requests_begin(struct mxl_mgmt_requests *s, const void *connection,
                            int kind, int restricted)
{
    unsigned i, count = 0, empty = MXL_MGMT_REQUEST_SLOTS;
    if (!s || !connection || s->fault) return 503;
    for (i = 0; i < MXL_MGMT_REQUEST_SLOTS; i++) {
        if (s->connection[i] == connection) {
            s->fault = 1; return 503; /* Missing end callback / unsafe reuse. */
        }
        if (s->connection[i]) count++;
        else empty = i;
    }
    if (count != s->count) { s->fault = 1; return 503; }
    if (kind == MXL_MGMT_REQUEST_READ || kind == MXL_MGMT_REQUEST_CONTROL) return 0;
    if (restricted) return 409;
    if (empty == MXL_MGMT_REQUEST_SLOTS) return 503;
    s->connection[empty] = connection; s->count++;
    return 0;
}
void mxl_mgmt_requests_end(struct mxl_mgmt_requests *s, const void *connection)
{
    unsigned i;
    if (!s || !connection) return;
    for (i = 0; i < MXL_MGMT_REQUEST_SLOTS; i++) {
        if (s->connection[i] != connection) continue;
        s->connection[i] = 0;
        if (!s->count) s->fault = 1;
        else s->count--;
        return;
    }
    /* Safe/read/rejected requests also receive end_request. No lease to free. */
}
