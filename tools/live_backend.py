"""V2 operation contracts. No browser-supplied URLs or arbitrary register writes."""
from dataclasses import dataclass
import ipaddress
import json
import re
import struct
from switch_transport import SwitchError

@dataclass(frozen=True)
class Read:
    path: str
    method: str = 'GET'
    stream: bool = False

READS = {key: Read('/' + path + '.json', method, stream) for key, path, method, stream in [
    ('status','status','GET',False),('ports','port_setting_load','GET',False),
    ('statistics','port_statistics','GET',False),('network','network_settings','GET',False),
    ('pvid','port_vlan','GET',False),('vlans','tag_vlan','GET',True),
    ('stp','stp','GET',False),('loop','port_lock_cfg','GET',False),
    ('loop-status','port_loop_status','GET',False),('lag','port_trunk_cfg','GET',False),
    ('lag-status','port_trunk_refresh','GET',False),('mirror','port_mirror','GET',False),
    ('mac-dynamic','mac_get_dynamic_mac_entries','GET',True),
    ('mac-static','mac_get_static_mac_entries','GET',True),
    ('igmp','igmp_config','GET',False),('igmp-router','igmp_rp_config','GET',False),
    ('igmp-querier','igmp_query_config','GET',False),('igmp-groups','igmp_get_entries','GET',True),
    ('storm','storm_ctrl_cfg','GET',False),('lldp','lldp_loadsts','POST',False),
    ('neighbors','lldp_fetch_rx_data','POST',False),('eee','eee_config','GET',False),
    ('dhcp','dhcp_snooping_cfg','GET',False),('sntp','sntp_setting','GET',False),
    ('clock','systemtime_settings','GET',False),('qos-rates','qos_get_rate_limit','GET',False),
    ('qos-mode','qos_get_port_mode','GET',False),('qos-priority','qos_get_port_priority','GET',False),
    ('qos-queues','qos_queue_sched','GET',False),('qos-tc','qos_get_tc_q_map','GET',False),
    ('qos-dscp','qos_get_dscp_tc_map','GET',False),('qos-cos','qos_get_cos_tc_map','GET',False),
]}
FEATURES = [
    ('dash','Overview',['status','ports','statistics','lldp']),
    ('ports','Ports',['ports']),('statistics','Statistics',['statistics']),
    ('vlans','VLANs & PVID',['vlans','pvid']),('stp','Spanning tree',['stp']),
    ('loop','Loop protection',['loop','loop-status']),('lag','Aggregation',['lag','lag-status']),
    ('mirror','Port mirroring',['mirror']),('mac','MAC addresses',['mac-dynamic','mac-static']),
    ('igmp','Multicast',['igmp','igmp-router','igmp-querier','igmp-groups']),
    ('lldp','LLDP & neighbors',['lldp','neighbors']),('sfp','SFP modules',['ports']),('storm','Storm control',['storm']),
    ('qos','Quality of service',['qos-rates','qos-mode','qos-priority','qos-queues','qos-tc','qos-dscp','qos-cos']),
    ('dhcp','DHCP snooping',['dhcp']),('eee','Energy efficiency',['eee']),
    ('system','Identity & management',['network']),('time','Clock & SNTP',['clock','sntp']),
    ('config','Configuration & backup',[]),('firmware','Firmware',[]),
    ('capabilities','Terminal & CLI',[]),('logs','Activity',[]),
]

def integer(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{label} must be an integer from {lo} to {hi}')
    return value

def text(value, limit, label):
    if not isinstance(value, str) or len(value.encode()) > limit or any(ord(x) < 32 for x in value):
        raise ValueError(f'{label} must be at most {limit} UTF-8 bytes without control characters')
    return value

def choice(value, values, label):
    if value not in values:
        raise ValueError(f'Invalid {label}')
    return value

def ports(value, empty=False):
    if not isinstance(value, list) or (not empty and not value) or len(set(value)) != len(value):
        raise ValueError('Select distinct ports')
    return [integer(x,1,10,'Port') for x in value]

def boolean(value):
    if type(value) is not bool:
        raise ValueError('Expected a boolean')
    return value

def settings_identity(data):
    """Bounded extraction of identity records from the OEM exported config.

    This is a read-only projection, not a complete config parser or checksum
    validator. Other settings (including account data) are never returned.
    """
    result = {}
    if data[:4] != bytes.fromhex('23ce8af4'):
        raise ValueError('Unrecognized OEM configuration export')
    for name, key in [('name',b'sys/mxl_dev_desc'),('location',b'sys/location'),
                      ('contact',b'sys/contact'),('description',b'sys/description')]:
        needle=key+b'='
        start=0
        while (offset:=data.find(needle,start)) >= 0:
            p=offset+len(needle);start=p
            if p+4>len(data):continue
            length=struct.unpack_from('<I',data,p)[0]
            if not 0<length<=256 or p+4+length>len(data):continue
            try:value=data[p+4:p+4+length].split(b'\0',1)[0].decode('utf-8')
            except UnicodeError:continue
            result[name]=value
    return result

# An operation becomes available only after its request contract is recovered.
# Lists returned here are sent sequentially. Failures never trigger automatic retries.
def plan(action, a):
    port=lambda:integer(a.get('port'),1,10,'Port')
    request=lambda route, body: {'path':'/'+route+'.json','method':'POST','body':body}
    result=[];readback=None
    if action=='ports':
        pp=ports(a.get('ports'));speed=choice(a.get('speed'),['Auto','10Mbps Half','10Mbps Full','100Mbps Half','100Mbps Full','1000Mbps Full','2500Mbps Full','10Gbps Full'],'speed')
        if any(p<=8 for p in pp) and speed=='10Gbps Full':raise ValueError('Copper ports support up to 2.5G')
        status='Enable' if boolean(a.get('enabled')) else 'Disable';flow='On' if boolean(a.get('flow')) else 'Off'
        copper=[p for p in pp if p<=8];optical=[p for p in pp if p>8]
        if copper:result.append(request('apply_user_port_setting',dict(port_sts=status,port_spd_duplex=speed,flow_ctrl=flow,port_num=len(copper),port_list=[str(p) for p in copper])))
        if optical:
            if speed not in ['Auto','1000Mbps Full','2500Mbps Full','10Gbps Full']:raise ValueError('Unsupported SFP speed')
            result.append(request('apply_ext_port_setting',dict(port_sts=[status]*len(optical),port_spd_duplex=[speed]*len(optical),flow_ctrl=[flow]*len(optical),mode=[0]*len(optical),port_list=[str(p) for p in optical])))
        readback='ports'
    elif action=='lldp':
        enabled=ports(a.get('ports'),empty=True)
        # Disable only ports currently enabled; pass current state from backend.
        current=a.get('_current',{})
        disable=[p for p in range(1,11) if current.get(f'Port_{p}') and p not in enabled]
        enable=[p for p in enabled if not current.get(f'Port_{p}')]
        if disable:result.append(request('lldp_disable',disable))
        if enable:result.append(request('lldp_enable',enable))
        readback='lldp'
    elif action=='name':
        name=text(a.get('name'),16,'Switch name')
        if not name.strip():raise ValueError('Switch name cannot be blank')
        result=[request('set_des',{'input_des':name})];readback='identity'
    elif action=='pvid':
        result=[request('port_vlan',{'port_based_vlan_frame_type':str(integer(a.get('frame'),0,2,'Frame acceptance')),'port_based_vlan_pvid_input':str(integer(a.get('pvid'),1,4094,'PVID')),'port_based_vlan_selection':[str(p) for p in ports(a.get('ports'))]})];readback='pvid'
    elif action=='port-defaults':
        groups={};current=a.get('_current',{})
        for p in range(1,11):
            vid=integer(a.get(f'pvid_{p}'),1,4094,'PVID');frame=integer(a.get(f'frame_{p}'),0,2,'Accepted frames')
            old=current.get(f'Port_{p}',{})
            if old.get('PVID')!=vid or old.get('Frame_Type')!=frame:groups.setdefault((vid,frame),[]).append(p)
        for (vid,frame),pp in groups.items():
            planned,_=plan('pvid',{'ports':pp,'pvid':vid,'frame':frame});result+=planned
        readback='pvid'
    elif action=='vlan':
        states=a.get('states')
        if not isinstance(states,list) or len(states)!=10:raise ValueError('Provide ten VLAN membership states')
        states=[integer(x,0,2,'Membership') for x in states]
        if not any(states):raise ValueError('VLAN needs at least one member')
        result=[request('tag_vlan',{'deletedVlans':[],'updatedVlans':[{'port_states':[0]+states,'vlan_id':str(integer(a.get('vid'),1,4094,'VLAN')),'vlan_name':text(a.get('name',''),16,'VLAN name')}]})];readback='vlans'
        selected=ports(a.get('pvidPorts',[]),empty=True)
        if any(states[p-1]!=1 for p in selected):raise ValueError('Assign PVID only to untagged members')
        groups={}
        for p in selected:
            old=a.get('_currentPvid',{}).get(f'Port_{p}',{})
            if 'Frame_Type' not in old:raise ValueError('Current port defaults are required before assigning PVID')
            if old.get('PVID')!=a['vid']:groups.setdefault(old['Frame_Type'],[]).append(p)
        for frame,pp in groups.items():
            planned,_=plan('pvid',{'ports':pp,'pvid':a['vid'],'frame':frame});result+=planned
    elif action=='vlan-delete':
        vid=integer(a.get('vid'),2,4094,'VLAN to delete')
        result=[request('tag_vlan',{'deletedVlans':[vid],'updatedVlans':[]})];readback='vlans'
    elif action=='stp':
        body={'stp_enable':'1' if boolean(a.get('enabled')) else '0','stp_rstp_mode':choice(a.get('mode'),['STP','RSTP'],'STP mode'),'loop_stp_sel':'stp','detect_enable':'0'}
        for p in ports(a.get('edge',[]),empty=True):body[f'psel_cbox{p}']='on'
        result=([request('port_lock_cfg',{'cPrev':'off','detect_enable':'0'})] if a['enabled'] else [])+[request('stp',body)];readback='stp'
    elif action=='loop':
        enabled=boolean(a.get('enabled'))
        body={'cPrev':'on' if enabled else 'off','detect_enable':'1' if enabled else '0','stp_enable':'0','loop_stp_sel':'loop','time_interval':str(integer(a.get('interval'),1,3600,'Detection interval')),'recover_time':str(integer(a.get('recovery'),1,3600,'Recovery time'))}
        result=[request('port_lock_cfg',body)]+([request('stp',{'stp_enable':'0'})] if enabled else []);readback='loop'
    elif action=='lag':
        body={'system_priority':str(integer(a.get('priority'),0,65535,'System priority'))}
        groups={}
        for p in range(1,11):
            mode=integer(a.get('mode_'+str(p)),0,2,'Port mode')
            group=integer(a.get('group_'+str(p)),0,15,'LAG group')
            if mode:groups.setdefault(group,[]).append(p)
            body.update({f'portTypeId_{p}':str(mode),f'Port_{p}_grpInd':str(group),f'portPriorityId_{p}':str(integer(a.get('priority_'+str(p)),0,65535,'Port priority')),f'lacpTimeoutId_{p}':str(integer(a.get('timeout_'+str(p)),0,1,'LACP timeout'))})
        if any(len(v)<2 for v in groups.values()):raise ValueError('Each aggregation group requires at least two ports')
        for group,pp in groups.items():
            if len({a['mode_'+str(p)] for p in pp})>1:raise ValueError('Group members must use the same aggregation mode')
        result=[request('port_trunk_cfg',body)];readback='lag'
    elif action=='eee':
        desired=[int(boolean(a.get(f'port_{p}'))) for p in range(1,11)]
        old=a.get('_current',{})
        def enabled(v):return v in (1,True,'on','On','1')
        internal=[int(enabled(old.get(f'Idx_{i}',{}).get('eee_enable'))) for i in range(8)]
        external=[int(enabled(old.get(f'ext_Idx_{i}',{}).get('eee_enable'))) for i in range(2)]
        if desired[:8]!=internal:result.append(request('eee_config',{'int_port_en':desired[:8]}))
        if desired[8:]!=external:result.append(request('eee_config',{'ext_port_en':desired[8:]}))
        readback='eee'
    elif action=='dhcp':
        body={'dhcp_snooping_mode':str(integer(a.get('mode'),0,1,'Snooping mode'))}
        for p in range(1,11):
            limit=integer(a.get('limit_'+str(p)),0,400,'Rate limit')
            if limit and limit<100:raise ValueError('DHCP rate limit must be zero or 100–400')
            body.update({f'portTypeId_{p}':str(integer(a.get('trust_'+str(p)),0,1,'Trust')),f'Port_{p}_rateLimit':str(limit)})
        result=[request('dhcp_snooping_cfg',body)];readback='dhcp'
    elif action=='mirror':
        dest=integer(a.get('destination'),0,10,'Monitor port');pp=ports(a.get('ports'),empty=True)
        if dest in pp:raise ValueError('Monitor port cannot mirror itself')
        if pp and not dest:raise ValueError('Select a monitor port')
        result=[request('port_mirror',{'mirroring_port_selection':str(dest),'mirrored_port_selection':[str(p) for p in pp],'Ingress_Status':'1' if boolean(a.get('ingress')) else '0','Egress_Status':'1' if boolean(a.get('egress')) else '0'})];readback='mirror'
    elif action=='storm':
        result=[request('storm_ctrl_cfg',{'port':port(),'state':1 if boolean(a.get('enabled')) else 0,'rate':integer(a.get('rate'),1,1000,'Storm rate'),'storm_type':choice(a.get('type'),['broadcast','multicast','unknown_unicast','unknown_multicast'],'storm type')})];readback='storm'
    elif action=='igmp':
        result=[request('igmp_config',{'igmp':'on' if boolean(a.get('enabled')) else 'off','fast-leave':'on' if boolean(a.get('fastLeave')) else 'off','report-flood':'on' if boolean(a.get('reportFlood')) else 'off'})];readback='igmp'
    elif action=='igmp-router':
        result=[request('igmp_rp_config',{'vlan_id':str(integer(a.get('vid'),1,4094,'VLAN')),'port_id':str(port())})];readback='igmp-router'
    elif action=='igmp-querier':
        address=str(ipaddress.IPv4Address(a.get('address')))
        if not ipaddress.IPv4Address(address).is_multicast:raise ValueError('IGMP query address must be multicast')
        result=[request('igmp_query_config',{'vlan_id':str(integer(a.get('vid'),1,4094,'VLAN')),'igmp_version':str(choice(a.get('version'),[2,3],'IGMP version')),'protocol_type':'IGMP','query_ip':address})];readback='igmp-querier'
    elif action=='qos-mode':
        mode=choice(a.get('mode'),['def_pc','dscp_only','cos_only','dscp_then_cos','cos_then_dscp'],'classification mode')
        result=[request('qos_set_port_mode',{'qos_mode':mode})];readback='qos-mode'
    elif action=='dscp':
        result=[request('qos_set_dscp_tc_map',{'dscp_value':integer(a.get('dscp'),0,63,'DSCP'),'priority':integer(a.get('priority'),0,7,'Traffic class')})];readback='qos-dscp'
    elif action=='rate':
        result=[request('qos_set_rate_limit',{'port_id':port(),'in_meter_rate':integer(a.get('ingress'),0,10000,'Ingress Mbit/s'),'out_shaper_rate':integer(a.get('egress'),0,10000,'Egress Mbit/s')})];readback='qos-rates'
    elif action=='priority':
        result=[request('qos_set_port_priority',{'Port_Id':port(),'Priority':integer(a.get('priority'),0,7,'Priority')})];readback='qos-priority'
    elif action=='tc-queue':
        result=[request('qos_set_tc_q_map',{'port_id':port(),'Priority':integer(a.get('priority'),0,7,'Traffic class'),'queue_id':integer(a.get('queue'),0,7,'Queue')})];readback='qos-tc'
    elif action=='cos':
        values=a.get('values')
        if not isinstance(values,list) or len(values)!=16:raise ValueError('Provide all 16 CoS entries')
        result=[request('qos_set_cos_tc_map',{f'tc_input{i}':integer(v,0,7,'Traffic class') for i,v in enumerate(values)})];readback='qos-cos'
    elif action=='queue':
        result=[request('qos_queue_sched',{'port_id':port(),'priority_queue':integer(a.get('queue'),0,7,'Queue'),'weight':integer(a.get('weight'),0,15,'Scheduler value')})];readback='qos-queues'
    elif action=='clock':
        from datetime import datetime
        date=text(a.get('date'),10,'Date');time=text(a.get('time'),8,'Time');offset=text(a.get('offset'),6,'UTC offset')
        datetime.strptime(date+' '+time,'%m/%d/%Y %H:%M:%S')
        if not re.fullmatch(r'[+-](?:0[0-9]|1[0-4]):[0-5][0-9]',offset):raise ValueError('Invalid UTC offset')
        result=[request('systemtime_settings',{'input_date':date,'input_time':time,'timezone_offset':offset,'input_daylight':'on' if boolean(a.get('daylight')) else 'off'})];readback='clock'
    elif action=='account':
        import hashlib
        username=text(a.get('username'),32,'Username');current=text(a.get('current'),64,'Current password');password=text(a.get('password'),64,'New password')
        if not username or not password or password!=a.get('confirm'):raise ValueError('Provide a username and matching new passwords')
        digest=lambda x:hashlib.md5(x.encode()).hexdigest()
        result=[request('user_ac_cfg',{'usr':digest(username),'new_pwd':digest(password),'cur_pwd':digest(current)})];readback=None
    elif action=='sntp':
        server=text(a.get('server',''),46,'SNTP server')
        if a.get('enabled') and not server:raise ValueError('SNTP server required')
        result=[request('sntp_setting',{'sntp_state':'1' if boolean(a.get('enabled')) else '0','sntp_poll':str(integer(a.get('interval'),16,86400,'Polling interval')),'sntp_server_ip':server})];readback='sntp'
    elif action=='network':
        body={'dhcp_enable':'1' if boolean(a.get('dhcp')) else '0','input_ip':str(ipaddress.IPv4Address(a.get('ip'))),'input_netmask':str(ipaddress.IPv4Network('0.0.0.0/'+a.get('mask')).netmask),'input_gateway':str(ipaddress.IPv4Address(a.get('gateway'))),'auto_dns':'1' if boolean(a.get('autoDns')) else '0','dns_server':str(ipaddress.IPv4Address(a.get('dns')))}
        result=[request('network_settings_ipv4',body)];readback=None
    elif action=='mac-delete':
        mac=text(a.get('mac'),17,'MAC address').upper()
        if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}',mac):raise ValueError('Invalid MAC address')
        result=[request('mac_delete_static_mac_entries',{'mac_addr_txt':[mac],'vlan_text':[str(integer(a.get('vid'),1,4094,'VLAN'))]})];readback='mac-static'
    elif action=='mac-add':
        mac=text(a.get('mac'),17,'MAC address').upper()
        if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}',mac) or int(mac[:2],16)&1:raise ValueError('Enter a unicast MAC address')
        result=[request('mac_add_static_mac_entries',{'mac-input':mac,'vlan-input':str(integer(a.get('vid'),1,4094,'VLAN')),'port-input':str(port())})];readback='mac-static'
    elif action in ('clear-statistics','mac-flush','save','reboot'):
        route={'clear-statistics':'clear_statistics','mac-flush':'mac_clear_dynamic_mac_entries','save':'save_all_configs','reboot':'system_reboot'}[action]
        result=[request(route,{})];readback={'clear-statistics':'statistics','mac-flush':'mac-dynamic'}.get(action)
    else:
        raise ValueError('Operation has no established request contract')
    return result,readback

def verify_readback(action,a,d):
    """True/False only for established comparisons; None means unverified."""
    enabled=lambda v:v in (True,1,'1','on','On','Enabled','Enable')
    if action=='lldp':return all(d.get(f'Port_{p}') is (p in a['ports']) for p in range(1,11))
    if action=='ports':
        for p in a['ports']:
            r=d.get(f'Port_{p}',{})
            norm=lambda x:str(x).replace(' ','').replace('10Gbps','10000Mbps')
            if enabled(r.get('Port_Status'))!=a['enabled'] or enabled(r.get('Flow_Ctrl_Cfg'))!=a['flow'] or norm(r.get('Spd_Duplex_Cfg'))!=norm(a['speed']):return False
        return True
    if action=='port-defaults':return all(d.get(f'Port_{p}',{}).get('PVID')==a[f'pvid_{p}'] and d.get(f'Port_{p}',{}).get('Frame_Type')==a[f'frame_{p}'] for p in range(1,11))
    if action=='pvid':return all(d.get(f'Port_{p}',{}).get('PVID')==a['pvid'] and d.get(f'Port_{p}',{}).get('Frame_Type')==a['frame'] for p in a['ports'])
    if action in ('vlan','vlan-delete'):
        records=[x for x in d if isinstance(x,dict) and x.get('vlan_id')==a['vid']]
        if action=='vlan-delete':return not records
        return bool(records) and records[0].get('port_states')==a['states'] and records[0].get('vlan_name')==a.get('name','') and all(records[0].get('port_pvids',[])[p-1:p]==[a['vid']] for p in a.get('pvidPorts',[]))
    if action=='stp':return enabled(d.get('stp_enable'))==a['enabled'] and d.get('stp_rstp_mode')==a['mode'] and all(enabled(d.get(f'Port_{p}',{}).get(f'Stp_Edge_{p}'))==(p in a['edge']) for p in range(1,11))
    if action=='loop':return enabled(d.get('cPrev'))==a['enabled'] and int(d.get('time_interval',-1))==a['interval'] and int(d.get('recover_time',-1))==a['recovery']
    if action=='mirror':return int(d.get('MonitoringPortId',-1))==a['destination'] and all(enabled(d.get(f'Port_{p}',{}).get('Ingress_Status'))==(p in a['ports'] and a['ingress']) and enabled(d.get(f'Port_{p}',{}).get('Egress_Status'))==(p in a['ports'] and a['egress']) for p in range(1,11))
    if action=='igmp':return enabled(d.get('igmp'))==a['enabled'] and enabled(d.get('fast_leave'))==a['fastLeave'] and enabled(d.get('report_flood'))==a['reportFlood']
    if action=='rate':
        r=next((x for x in d.get('ports',[]) if x.get('port_id')==a['port']),{})
        return r.get('in_rate')==a['ingress'] and r.get('out_rate')==a['egress']
    if action=='priority':return d.get(f"Port_{a['port']}",{}).get('Priority')==a['priority']
    if action=='tc-queue':return any(x.get('Priority')==a['priority'] and x.get('QueueID')==a['queue'] for x in d.get(f"Port_{a['port']}",[]))
    if action=='queue':return any(x.get('PriorityQueue')==a['queue'] and x.get('Weight')==a['weight'] for x in d.get(f"Port_{a['port']}",[]))
    if action=='dscp':return int(d.get(f"Idx_{a['dscp']}",{}).get('Mapped_Tc',-1))==a['priority']
    if action=='cos':return all(int(d.get(f'Idx_{i}',{}).get('Mapped_Tc',-1))==v for i,v in enumerate(a['values']))
    if action=='qos-mode':return d.get('qos_mode')=={'def_pc':0,'dscp_only':1,'cos_only':5,'dscp_then_cos':7,'cos_then_dscp':6}[a['mode']]
    if action=='sntp':return enabled(d.get('sntp_state'))==a['enabled'] and int(d.get('sntp_poll',-1))==a['interval'] and d.get('sntp_server_ip')==a['server']
    if action=='eee':return all(enabled(d.get(f'Idx_{p-1}' if p<=8 else f'ext_Idx_{p-9}',{}).get('eee_enable'))==a[f'port_{p}'] for p in range(1,11))
    if action=='dhcp':return int(d.get('snooping_mode',-1))==a['mode'] and all(int(d.get(f'Port_{p}',{}).get(f'portTypeId_{p}',-1))==a['trust_'+str(p)] and int(d.get(f'Port_{p}',{}).get(f'Port_{p}_rateLimit',-1))==a['limit_'+str(p)] for p in range(1,11))
    if action=='lag':return int(d.get('system_priority',-1))==a['priority'] and all(all(int(d.get(f'Port_{p}',{}).get(k,-1))==a[f'{arg}_{p}'] for k,arg in [(f'portTypeId_{p}','mode'),(f'portPriorityId_{p}','priority'),(f'lacpTimeoutId_{p}','timeout'),(f'Port_{p}_grpInd','group')]) for p in range(1,11))
    # Native name endpoint sets runtime data; identity export reads saved data.
    # Clock advances, and some tables require stateful pagination. Do not claim verification.
    return None

class Backend:
    def __init__(self,transport):
        self.transport=transport
    def read(self,key):
        if key=='identity':
            r=self.transport.request('/config/download',binary=True)
            return {'data':settings_identity(r['bytes']),'source':'saved OEM configuration; runtime name may differ until saved'}
        if key not in READS:raise ValueError('Unknown read operation')
        r=READS[key]
        return self.transport.request(r.path,method=r.method,stream=r.stream)
    def apply(self,action,args):
        with self.transport.lock:
            if action=='lldp':args={**args,'_current':self.read('lldp')['data']}
            if action=='eee':args={**args,'_current':self.read('eee')['data']}
            if action=='port-defaults':args={**args,'_current':self.read('pvid')['data']}
            if action=='vlan' and args.get('pvidPorts'):args={**args,'_currentPvid':self.read('pvid')['data']}
            requests,readback=plan(action,args)
            completed=[]
            try:
                for index,r in enumerate(requests):
                    result=self.transport.request(**r,allow_empty=True)
                    if isinstance(result.get('data'),dict) and str(result['data'].get('alert_key','')).startswith('alert_') and result['data']['alert_key']!='alert_success':
                        raise SwitchError('Switch rejected settings: '+str(result['data']))
                    completed.append({'path':r['path'],'acknowledged':not result.get('empty_reply'), 'response':result.get('data')})
                    if action=='vlan' and index==0 and len(requests)>1:
                        check={**args,'pvidPorts':[]}
                        if verify_readback('vlan',check,self.read('vlans')['data']) is not True:raise SwitchError('VLAN membership did not verify; PVID updates were not sent')
                if action=='eee' and requests:
                    import time
                    time.sleep(0.1)  # OEM acknowledges before the delayed PHY configuration.
                observed=self.read(readback) if readback else None
            except Exception as error:
                raise SwitchError(f'{error}. {len(completed)} request(s) completed; device state may have changed. Refresh before retrying.') from error
            verified=verify_readback(action,args,observed['data']) if observed else None
            return {'completed':completed,'readback':observed,'verified':verified,'persistence':'Save configuration explicitly; LLDP handler also attempts its own save. Reboot persistence untested.','notice':('Readback matches requested settings.' if verified is True else 'Readback differs from requested settings.' if verified is False else 'Readback returned; comparison is not established for this operation.' if observed else 'Request sent; readback unavailable. Verify device state.')}
