"""Public synthetic fixtures. Every row contains a distinct bilingual fact."""

ACCOUNTS = [
    ("employee", "林澄", "普通员工", "运营部"),
    ("engineer", "陈砚", "研发人员", "研发部"),
    ("peer", "夏禾", "研发人员", "研发部"),
    ("hr", "周宁", "HR", "人事部"),
    ("admin", "许岚", "管理员", "平台部"),
]
DEPARTMENTS = {a[3] for a in ACCOUNTS}
DEMO_PASSWORD = "Orchid-Demo-26"

# title | English topic | Chinese fact | English fact
PUBLIC = """
访客登记|Visitor pass|访客登记点设在青禾前台。|The visitor desk is at Green Hall.
员工手册|Staff handbook|新员工应在入职后五天内完成手册签收。|Sign the handbook within five days of joining.
差旅报销|Travel expenses|差旅报销应在返程后十二天内提交。|File travel expenses within twelve days of return.
设备报修|Device repair|设备报修工单分配给松针服务台。|Send repair tickets to Pine Desk.
远程办公|Remote work|远程办公每周最多两天。|Remote work is limited to two days per week.
会议室预约|Meeting rooms|会议室预约最多提前九天。|Book rooms up to nine days ahead.
安全培训|Security training|年度安全培训的完成月份是四月。|Complete annual security training in April.
门禁挂失|Badge loss|门禁挂失请联系白桦柜台。|Report a lost badge to Birch Desk.
图书借阅|Library loans|图书借阅期限为二十一天。|Library loans last twenty-one days.
消防集合|Fire assembly|消防演练集合地点为北侧草坪。|The fire assembly point is the north lawn.
软件申请|Software request|软件申请使用紫藤表单。|Submit software requests with the Wisteria form.
食堂午餐|Lunch hours|食堂午餐在十一点四十开始。|Lunch starts at 11:40.
班车发车|Shuttle departure|园区班车在南门发车。|The shuttle leaves from the south gate.
环保回收|Recycling|电池回收箱位于一楼茶水间。|Battery recycling is on the first floor.
档案归还|Archive returns|档案归还时填写银杏登记簿。|Use the Ginkgo register for archive returns.
网络报障|Network outage|网络报障分机为六零三。|Call extension 603 for network outages.
志愿活动|Volunteer day|志愿活动固定在十月。|Volunteer day takes place in October.
印章预约|Seal booking|印章预约需提前三个工作日。|Book the seal three working days ahead.
"""
HR = """
薪酬复核|Salary review|薪酬复核的内部校验码是 HR-ORCHID-72。|The salary review code is HR-ORCHID-72.
面试备案|Interview register|面试备案使用栀子登记册。|Record interviews in the Gardenia register.
导师津贴|Mentor allowance|导师津贴每期三百四十星币。|Mentor allowance is 340 credits per cycle.
调岗审批|Transfer approval|调岗审批由杜鹃小组复核。|Azalea reviews transfer requests.
离职面谈|Exit interview|离职面谈须在交接前三天预约。|Book an exit interview three days before handover.
试用期回访|Probation check|试用期回访安排在第七周。|The probation check is in week seven.
人才盘点|Talent census|人才盘点的模板编号为 TAL-19。|The census template is TAL-19.
绩效复议|Performance appeal|绩效复议窗口为八个工作日。|The appeal window is eight working days.
培训预算|Training budget|培训预算归入琥珀账本。|Record training budgets in the Amber ledger.
招聘渠道|Hiring channels|招聘渠道评审每季度举行一次。|Review hiring channels quarterly.
体检安排|Health screening|体检名单在二月核对。|Verify the screening roster in February.
薪级映射|Pay bands|薪级映射表的版本代号是 MAPLE-14。|The band map revision is MAPLE-14.
年度留任|Retention review|年度留任分析采用蓝鸢尾分组。|Retention analysis uses Blue Iris cohorts.
奖金封存|Bonus archive|奖金封存批次号为 BONUS-38。|The archive batch is BONUS-38.
岗位定级|Position grading|岗位定级委员会在周三评议。|The grading committee meets on Wednesday.
调薪清册|Raise roster|调薪清册由铃兰组保管。|Lily Desk holds the raise roster.
"""
RD = """
星桥发布|Starbridge release|星桥发布的验收口令是 RD-CEDAR-41。|The Starbridge release marker is RD-CEDAR-41.
流水线回滚|Pipeline rollback|流水线回滚保留七个快照。|Rollback retains seven snapshots.
构建签名|Build signing|构建签名使用代号 FIR-06。|Build signing uses FIR-06.
流量回放|Traffic replay|流量回放窗口为十五分钟。|The replay window is fifteen minutes.
固件烧录|Firmware flash|固件烧录台编号为 FEN-18。|The flash station is FEN-18.
接口压测|Load test|接口压测持续四十五分钟。|The load test lasts forty-five minutes.
依赖审查|Dependency review|依赖审查基线是 ASH-81。|The baseline is ASH-81.
灰度发布|Canary rollout|灰度发布的首轮比例为百分之三。|The initial canary is three percent.
镜像留存|Image retention|镜像留存周期为十九天。|Retain images for nineteen days.
密钥轮换|Key rotation|实验密钥轮换周期为三十一天。|Rotate lab keys every thirty-one days.
故障演练|Fault drill|故障演练场地代号为 MARSH-17。|The drill site is MARSH-17.
缓存清理|Cache sweep|缓存清理在凌晨三时执行。|Sweep caches at 03:00.
蓝图归档|Blueprint archive|蓝图归档的盒号为 QUARTZ-39。|The archive box is QUARTZ-39.
采样批次|Sampling batch|采样批次标记为 SAMPLE-66。|The batch marker is SAMPLE-66.
数据校准|Sensor calibration|数据校准采用十三轮采样。|Calibrate with thirteen sampling rounds.
隔离试验|Isolation experiment|隔离试验的观测标识是 TEST-MOSS-24。|The observation marker is TEST-MOSS-24.
"""


def corpus():
    for prefix, table, dept in [("PUB", PUBLIC, "运营部"), ("HR", HR, "人事部"), ("RD", RD, "研发部")]:
        for i, line in enumerate(table.strip().splitlines(), 1):
            title, english, fact, translation = line.split("|")
            target = "hr" if prefix == "HR" else "engineer"
            # RD-001 starts sealed to support the grant/revoke demonstration.
            people = [target] if prefix != "PUB" and i > 10 else []
            departments = [dept] if prefix != "PUB" and i <= 10 and (prefix, i) != ("RD", 1) else []
            yield {
                "id": f"{prefix}-{i:03}",
                "title": title,
                "dept": dept,
                "owner": "admin",
                "public": prefix == "PUB",
                "departments": departments,
                "users": people,
                "filename": f"{prefix}-{i:03}.md",
                "raw": f"{title} / {english}\n{fact}\n{translation}".encode(),
            }
