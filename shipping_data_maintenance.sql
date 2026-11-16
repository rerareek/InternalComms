-- Run once in Supabase SQL Editor. Existing records are preserved.
create table if not exists public.shipping_data_maintenance (
    service_name text primary key,
    no integer,
    consortium text,
    "window" text,
    loa text,
    berth text,
    ave_volume_per_call text,
    port_rotation text,
    phase_in text,
    phase_out text,
    remark text,
    sort_order integer not null default 0,
    updated_at timestamptz not null default now()
);
create index if not exists shipping_data_maintenance_order_idx on public.shipping_data_maintenance(sort_order);
alter table public.shipping_data_maintenance enable row level security;
-- Uses existing Streamlit service_role key; do not expose service_role in client/browser.
-- Seed only missing services. Source values retained as supplied.
insert into public.shipping_data_maintenance
(no,service_name,consortium,"window",loa,berth,ave_volume_per_call,port_rotation,phase_in,phase_out,remark,sort_order)
values
(1,'CIN1','CMA, COSCO, OOCL','SAT 00:00 - SUN 01:00','294 M','NORTH','5000 Teus','JKT - SUB- DVO -SHA - NGB - SHK-NSA-QIN','','','',1),
(2,'JID','ONE','SAT 07.00 - MON 01.00','295 M','NORTH','4000 Teus','JKT-SIN-HCM-TYO-KWS-YOK-YKK-NGO-UKB-SIN','Maiden call on May 2023','JSJ (Hapag) Phase out on early Feb 2025','Move to NPCT1',2),
(3,'CS1','CMA, WANHAI','FRI 15:00 - SUN 12:00','295 M','NORTH','3500 Teus','JKT-SIN-KAO-XMN-HKG-SHK-NSA-PKG(WEST) -PKL (NORTH) - SIN','','','',3),
(4,'KCS','CMA','WED 02.00 - THU 12.00','255 M','NORTH','2000 Teus','IDJKT-IDSUB-PHDVO-CNSHA-CNDLC-CNTXG-CNTAO-CNSWA-HKHKG-CNSHK-CNNSA-PHMNL-CNLYG-CNTAO-CNNSA-IDJKT','','','',4),
(5,'CSE','COSCO','THU 23:00 - SAT 15:00','264 M','NORTH','2500 Teus','JKT-SIN-MAN-TXG-DLC-TAO-NGB-NSA','','','',5),
(6,'NEW CTI','COSCO, GOLDSTAR, OOCL, YML','MON 08 00 - WED 04:00','269 M','NORTH','2200 Teus','JKT-SUB-KHH-SHA-NGB-DVO','','','',6),
(8,'KIS1','KMTC, SINOKOR, HEUNG A','WED 08:00 - THU 23:00','262 M','NORTH','2800 Teus','JKT-SUB-HKG-KAN-USN-PUS-PNC-HKG-SIN','','','',7),
(7,'PCI','SINOKOR, HEUNG A, JJS','SUN 07:00 - MON 11:00','208 M','WEST','2000 Teus','JKT-SUB-SGN-SHA-PUS-KAN-SHA','','','',8),
(9,'SI8 / AIS5','WANHAI, IAL, KMTC','TUE 07.00 - WED 07.00','222 M','WEST','1000 Teus','JKT-SUB-SIN-PKG-MUN-NSA-PKG-JKT','Maiden call on May 2024','','',9),
(10,'TIX / MTS','CMA, COSCO','FRI 20:00 - SAT 20:00','162 M','WEST','1200 Teus','JKT-PGU-SIN-BKK-LCH-SIN-JKT','','','',10),
(11,'CS2','CMA, ONE, RCL','THU 07.00 - THU 23.00','210 M','WEST','1500 Teus','JKT-PKL(NORTH)-PKG(WEST)-HKG-NSA-SHK-SUB-SMR','','RCL & ONE Phase out','Changes to CIM',11),
(12,'IHX','COSCO','SAT 02.00 - SUN 10.00','200 M','WEST','2500 Teus','JKT - SIN - HCM','','','',12),
(13,'CKI','KMTC','MON 07:00 - TUE 18:00','262 M','WEST','1200 Teus','JKT-SUB-SGN-SHA-PUS-KAN-SHA-NGB','','','',13),
(14,'CIM','ONE, RCL, WANHAI','THU 07.00 - THU 23.00','220 M','WEST','1500 Teus','JKT-PKL(NORTH)-PKG(WEST)-HKG-NSA-SHK-SUB-SMR','CIM maiden call on May 2025','','New consortium with WHL',14),
(15,'SEI1/JSI','COSCO, UNIFEEDER','WED 07:00 - FRI 01:00','263 M','WEST','600 Teus','JKT-SUB-PKG (WEST)','Maiden call (Unifeeder) on 14 Dec 2025','JSS(CMA) Phase out on March 2025','Change to KI-8',15),
(16,'KI-8 / SEA-7','CMA, CK-LINE, SEALEAD, PIL','WED 02:00 - THU 03:00','220 M','WEST','1800 Teus','BSN-INC-SHA-NGO-JKT-SMG-HCIMNH-BUSAN','Maiden call (CNC) on 3 October 2025','','New service KI-8',16),
(17,'JNS','HEDE','FLOATING WINDOW','180 M','WEST','1200 Teus','JKT-NSA-JKT','Maiden Call (Hede) on 11 November 2025','','',17),
(18,'KCI','SITC, TS LINE, ONE, NAMSUNG','MON 22.00 - WED 10.00','209 M','WEST','2700 Teus','','','Terminated on April 2025','Move to NPCT1',18),
(19,'JTH','SITC','','','WEST','','','','Terminated on April 2024','Move to NPCT1',19),
(20,'CMI','SITC','','','WEST','','','','Terminated on May 2024','Move to NPCT1',20),
(21,'TPIS','WANHAI','TUE 11:00 - WED 10:00','213 M','WEST','800 Teus','JKT-SRG-SUB-TPE-TXG-KHH-SWG-HKG-SHK','','Terminated on December 2025','Move TSJ',21)
on conflict (service_name) do nothing;
