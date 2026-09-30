import os, csv, io, json, hmac, hashlib, secrets
from datetime import datetime, timezone
from functools import wraps
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from flask import Flask, request, redirect, url_for, session, flash, render_template_string, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet, InvalidToken
try:
    from openai import OpenAI
except ImportError:
    OpenAI=None

app=Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32)),
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL','sqlite:///businessos.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1',
)
db=SQLAlchemy(app); bcrypt=Bcrypt(app); csrf=CSRFProtect(app)
limiter=Limiter(key_func=get_remote_address, app=app, default_limits=['300 per hour'], storage_uri=os.getenv('RATELIMIT_STORAGE_URI','memory://'))
key=os.getenv('FERNET_KEY')
if not key:
    key=Fernet.generate_key().decode(); print('WARNING: set FERNET_KEY before production use.')
fernet=Fernet(key.encode()); MODEL=os.getenv('OPENAI_MODEL','gpt-5.6-luna')

def utc(): return datetime.now(timezone.utc)
def enc(s): return fernet.encrypt((s or '').encode()).decode()
def dec(s):
    if not s:return ''
    try:return fernet.decrypt(s.encode()).decode()
    except InvalidToken:return '[encrypted data unavailable]'
def money(x): return f'${x:,.2f}'
def fnum(x,d=0):
    try:return float(x)
    except:return d
def iphash(ip): return hashlib.sha256((ip+app.config['SECRET_KEY']).encode()).hexdigest()

class Company(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(180),nullable=False); created_at=db.Column(db.DateTime,default=utc)
class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); company_id=db.Column(db.Integer,db.ForeignKey('company.id'),nullable=False,index=True)
    email=db.Column(db.String(255),nullable=False); password_hash=db.Column(db.String(255),nullable=False); role=db.Column(db.String(30),default='member'); created_at=db.Column(db.DateTime,default=utc); last_login_at=db.Column(db.DateTime)
    __table_args__=(db.UniqueConstraint('company_id','email',name='uq_company_email'),)
class Opportunity(db.Model):
    id=db.Column(db.Integer,primary_key=True); company_id=db.Column(db.Integer,db.ForeignKey('company.id'),nullable=False,index=True)
    customer=db.Column(db.String(255),nullable=False); kind=db.Column(db.String(100),default='Revenue Recovery'); priority=db.Column(db.String(20),default='MEDIUM')
    amount=db.Column(db.Float,default=0); estimated=db.Column(db.Float,default=0); status=db.Column(db.String(30),default='OPEN'); recovered=db.Column(db.Float,default=0)
    owner=db.Column(db.String(255),default=''); due_date=db.Column(db.String(30),default=''); notes=db.Column(db.Text,default=''); source=db.Column(db.String(60),default='manual'); created_at=db.Column(db.DateTime,default=utc); updated_at=db.Column(db.DateTime,default=utc,onupdate=utc)
class Audit(db.Model):
    id=db.Column(db.Integer,primary_key=True); company_id=db.Column(db.Integer,db.ForeignKey('company.id'),nullable=False,index=True); user_id=db.Column(db.Integer)
    action=db.Column(db.String(120)); entity=db.Column(db.String(80)); entity_id=db.Column(db.String(80)); ip_hash=db.Column(db.String(64)); meta=db.Column(db.Text,default='{}'); created_at=db.Column(db.DateTime,default=utc)
class Integration(db.Model):
    id=db.Column(db.Integer,primary_key=True); company_id=db.Column(db.Integer,db.ForeignKey('company.id'),nullable=False,index=True); name=db.Column(db.String(100)); kind=db.Column(db.String(50),default='webhook')
    endpoint=db.Column(db.Text); secret=db.Column(db.Text); active=db.Column(db.Boolean,default=True); created_at=db.Column(db.DateTime,default=utc)
class WebhookEvent(db.Model):
    id=db.Column(db.Integer,primary_key=True); company_id=db.Column(db.Integer,db.ForeignKey('company.id'),nullable=False,index=True); provider=db.Column(db.String(100)); event_id=db.Column(db.String(255)); payload_hash=db.Column(db.String(64)); created_at=db.Column(db.DateTime,default=utc)
    __table_args__=(db.UniqueConstraint('company_id','provider','event_id',name='uq_event'),)

def user(): return db.session.get(User,session.get('user_id')) if session.get('user_id') else None
def company(): u=user(); return db.session.get(Company,u.company_id) if u else None
def audit(action,entity='',eid='',meta=None):
    u=user(); c=company()
    if c: db.session.add(Audit(company_id=c.id,user_id=u.id if u else None,action=action,entity=entity,entity_id=str(eid),ip_hash=iphash(request.remote_addr or ''),meta=json.dumps(meta or {})))
def login_required(fn):
    @wraps(fn)
    def w(*a,**k):
        if not user(): return redirect(url_for('login',next=request.path))
        return fn(*a,**k)
    return w
def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        def w(*a,**k):
            if not user(): return redirect(url_for('login'))
            if user().role not in allowed: abort(403)
            return fn(*a,**k)
        return w
    return deco

def ai(prompt):
    if not os.getenv('OPENAI_API_KEY') or OpenAI is None:return None
    return OpenAI(api_key=os.getenv('OPENAI_API_KEY')).responses.create(model=MODEL,input=prompt).output_text

def draft(o):
    p=f'''Write a concise professional customer follow-up for revenue recovery. Customer: {o.customer}. Issue: {o.kind}. Amount: {money(o.amount)}. Estimated recovery: {money(o.estimated)}. Priority: {o.priority}. Due date: {o.due_date or "not specified"}. Do not invent facts, threats, invoice numbers, or payment terms. Ask for a concrete next step. Under 160 words.'''
    out=ai(p)
    return out or f'Subject: Follow-up regarding {o.kind}\n\nHi {o.customer},\n\nWe are following up regarding an outstanding business item of {money(o.amount)}. Please let us know the best next step so we can resolve this promptly.\n\nThank you.'

def signed(secret,body): return hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
def send_events(cid,event,data):
    body=json.dumps({'event':event,'timestamp':utc().isoformat(),'data':data},separators=(',',':')).encode(); results=[]
    for i in Integration.query.filter_by(company_id=cid,active=True).all():
        endpoint=dec(i.endpoint); secret=dec(i.secret)
        try:
            if urlparse(endpoint).scheme!='https': continue
            r=Request(endpoint,data=body,headers={'Content-Type':'application/json','X-BusinessOS-Signature':signed(secret,body)},method='POST')
            with urlopen(r,timeout=8) as x: results.append([i.name,x.status])
        except Exception as e: results.append([i.name,str(e)[:120]])
    return results

@app.after_request
def headers(r):
    r.headers['X-Content-Type-Options']='nosniff'; r.headers['X-Frame-Options']='DENY'; r.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    r.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    r.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return r

BASE='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{title}} Â· BusinessOS AI</title><style>
:root{--bg:#08101f;--p:#111b30;--p2:#172440;--b:#2b3b5e;--t:#edf2ff;--m:#9eabc7;--a:#7da1ff;--g:#42d39e;--r:#ff7180}*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#07101e,#101a31);color:var(--t);font-family:Inter,system-ui,sans-serif}.wrap{max-width:1350px;margin:auto;padding:26px}.nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.brand{font-size:23px;font-weight:900}.brand b{color:var(--a)}.links{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.links a,.btn{padding:9px 12px;border:1px solid var(--b);border-radius:10px;background:var(--p2);color:var(--t);text-decoration:none}.primary{background:var(--a)!important;color:#071021!important;border-color:transparent!important;font-weight:800}.good{background:var(--g)!important;color:#061a13!important;border-color:transparent!important;font-weight:800}.card{background:rgba(17,27,48,.9);border:1px solid var(--b);border-radius:16px;padding:20px;box-shadow:0 14px 40px #0003}.hero{background:linear-gradient(135deg,#182a50,#17386b);margin-bottom:16px}.grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(4,1fr)}.two{grid-template-columns:2fr 1fr}h1{font-size:31px;margin:0 0 8px}h2{margin-top:0}.muted{color:var(--m)}.small{font-size:12px}input,select,textarea{width:100%;padding:11px;margin:6px 0 12px;background:#0b1427;border:1px solid var(--b);border-radius:10px;color:var(--t)}textarea{min-height:130px}label{font-size:13px;color:var(--m)}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:11px;border-bottom:1px solid var(--b);font-size:14px}th{color:var(--m)}.badge{padding:4px 8px;border-radius:99px;font-size:11px;font-weight:800}.HIGH{background:#421922;color:#ffb6bf}.MEDIUM{background:#403417;color:#ffe19b}.LOW{background:#14392f;color:#aaf1d6}.flash{padding:11px;border:1px solid var(--b);background:var(--p);border-radius:10px;margin-bottom:12px}@media(max-width:900px){.kpis,.two,.row{grid-template-columns:1fr}}
</style></head><body><div class="wrap"><div class="nav"><div class="brand">BusinessOS <b>AI</b></div><div class="links">{% if u %}<span class="muted small">{{u.email}} Â· {{u.role}}</span><a href="{{url_for('dashboard')}}">Dashboard</a><a href="{{url_for('integrations')}}">Integrations</a><a href="{{url_for('audit')}}">Audit</a><a href="{{url_for('logout')}}">Log out</a>{% endif %}</div></div>{% for cat,msg in get_flashed_messages(with_categories=true) %}<div class="flash">{{msg}}</div>{% endfor %}{{body|safe}}</div></body></html>'''

def page(title,body,**ctx): return render_template_string(BASE,title=title,body=render_template_string(body,**ctx),u=user())
LOGIN='''<div class="card" style="max-width:470px;margin:70px auto"><h1>BusinessOS AI</h1><p class="muted">Secure revenue operations.</p><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><label>Email</label><input name="email" type="email" required><label>Password</label><input name="password" type="password" required><button class="btn primary" style="width:100%">Sign in</button></form><p class="small muted">New? <a href="{{url_for('register')}}">Create a company workspace</a></p></div>'''
REG='''<div class="card" style="max-width:520px;margin:50px auto"><h1>Create workspace</h1><p class="muted">First user becomes owner.</p><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><label>Company</label><input name="company" required><label>Email</label><input name="email" type="email" required><label>Password</label><input name="password" type="password" minlength="12" required><p class="small muted">Minimum 12 characters.</p><button class="btn primary">Create workspace</button></form></div>'''
DASH='''<div class="card hero"><div class="small muted">REVENUE OPERATIONS CONTROL CENTER</div><h1>Find leakage. Assign action. Prove recovered cash.</h1><p class="muted">AI-assisted revenue recovery with tenant isolation, auditability, encryption and integrations.</p><a class="btn primary" href="{{url_for('new')}}">+ Add opportunity</a> <a class="btn" href="{{url_for('import_csv')}}">Import CSV</a></div><div class="grid kpis"><div class="card"><div class="muted small">Recovery pipeline</div><h1>{{money(s.pipeline)}}</h1></div><div class="card"><div class="muted small">Recovered revenue</div><h1 style="color:#42d39e">{{money(s.recovered)}}</h1></div><div class="card"><div class="muted small">Recovery rate</div><h1>{{'%.1f'|format(s.rate)}}%</h1></div><div class="card"><div class="muted small">Open items</div><h1>{{s.open}}</h1></div></div><div class="grid two" style="margin-top:16px"><div class="card"><h2>Recovery queue</h2>{% if os %}<table><tr><th>Priority</th><th>Customer</th><th>Issue</th><th>Est.</th><th>Status</th><th></th></tr>{% for o in os %}<tr><td><span class="badge {{o.priority}}">{{o.priority}}</span></td><td>{{o.customer}}</td><td>{{o.kind}}</td><td>{{money(o.estimated)}}</td><td>{{o.status}}</td><td><a class="btn small" href="{{url_for('opp',oid=o.id)}}">Open</a></td></tr>{% endfor %}</table>{% else %}<p class="muted">No opportunities yet.</p>{% endif %}</div><div class="card"><h2>AI brief</h2><p style="white-space:pre-wrap;line-height:1.65">{{brief}}</p></div></div>'''
NEW='''<div class="card" style="max-width:820px;margin:auto"><h1>Add opportunity</h1><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><div class="row"><div><label>Customer</label><input name="customer" required></div><div><label>Type</label><select name="kind"><option>Overdue Invoice</option><option>Failed Payment</option><option>Dormant Customer</option><option>Renewal Risk</option><option>Pricing Leakage</option><option>Other</option></select></div></div><div class="row"><div><label>Priority</label><select name="priority"><option>HIGH</option><option selected>MEDIUM</option><option>LOW</option></select></div><div><label>At-risk amount</label><input name="amount" type="number" min="0" step=".01" required></div></div><div class="row"><div><label>Estimated recovery</label><input name="estimated" type="number" min="0" step=".01" required></div><div><label>Owner</label><input name="owner"></div></div><label>Due date</label><input name="due_date"><label>Notes (encrypted)</label><textarea name="notes"></textarea><button class="btn primary">Create</button></form></div>'''
OPP='''<div class="grid two"><div class="card"><div class="small muted">RECOVERY WORKFLOW</div><h1>{{o.customer}}</h1><p class="muted">{{o.kind}}</p><div class="grid kpis"><div class="card"><div class="small muted">At risk</div><b>{{money(o.amount)}}</b></div><div class="card"><div class="small muted">Estimated</div><b>{{money(o.estimated)}}</b></div><div class="card"><div class="small muted">Recovered</div><b style="color:#42d39e">{{money(o.recovered)}}</b></div><div class="card"><div class="small muted">Status</div><b>{{o.status}}</b></div></div><form method="post" action="{{url_for('update',oid=o.id)}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><div class="row"><div><label>Status</label><select name="status">{% for s in ['OPEN','IN_PROGRESS','PARTIAL','RECOVERED','LOST'] %}<option {% if o.status==s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></div><div><label>Recovered amount</label><input name="recovered" type="number" min="0" step=".01" value="{{o.recovered}}"></div></div><div class="row"><div><label>Owner</label><input name="owner" value="{{o.owner}}"></div><div><label>Due date</label><input name="due_date" value="{{o.due_date}}"></div></div><label>Internal notes</label><textarea name="notes">{{notes}}</textarea><button class="btn good">Save outcome</button></form></div><div><div class="card"><h2>AI follow-up</h2><p class="muted">Generate a customer-safe message.</p><form method="post" action="{{url_for('draft',oid=o.id)}}"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><button class="btn primary">Draft message</button></form>{% if message %}<textarea readonly>{{message}}</textarea>{% endif %}</div><div class="card" style="margin-top:16px"><h2>Workflow</h2><p class="muted">Identify â assign â contact â record outcome â measure cash.</p></div></div></div>'''
IMPORT='''<div class="card" style="max-width:850px;margin:auto"><h1>Import CSV</h1><p class="muted">Columns: customer, kind, priority, amount, estimated, owner, due_date, notes.</p><form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><input type="file" name="file" accept=".csv" required><button class="btn primary">Import</button></form></div>'''
INT='''<div class="grid two"><div class="card"><h1>Integrations</h1><p class="muted">Signed HTTPS webhooks. Endpoint and secret are encrypted at rest.</p>{% for i in items %}<div class="card" style="margin:10px 0"><b>{{i.name}}</b><div class="small muted">{{i.kind}} Â· active={{i.active}}</div></div>{% else %}<p class="muted">None configured.</p>{% endfor %}</div><div class="card"><h2>Add webhook</h2><form method="post"><input type="hidden" name="csrf_token" value="{{csrf_token()}}"><label>Name</label><input name="name" required><label>HTTPS endpoint</label><input name="endpoint" type="url" required><label>Signing secret</label><input name="secret" required><button class="btn primary">Save</button></form></div></div>'''
AUD='''<div class="card"><h1>Audit log</h1><p class="muted">Only this company's events are shown.</p><table><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Metadata</th></tr>{% for a in logs %}<tr><td class="small">{{a.created_at}}</td><td>{{a.user_id}}</td><td>{{a.action}}</td><td>{{a.entity}} #{{a.entity_id}}</td><td class="small">{{a.meta}}</td></tr>{% endfor %}</table></div>'''

@app.route('/')
def home(): return redirect(url_for('dashboard') if user() else url_for('login'))
@app.route('/register',methods=['GET','POST'])
@limiter.limit('10 per hour')
def register():
    if user(): return redirect(url_for('dashboard'))
    if request.method=='POST':
        cn=request.form.get('company','').strip(); email=request.form.get('email','').strip().lower(); pw=request.form.get('password','')
        if len(pw)<12 or not cn or not email: flash('Company, email and a 12+ character password are required.'); return page('Register',REG)
        c=Company(name=cn); db.session.add(c); db.session.flush(); u=User(company_id=c.id,email=email,password_hash=bcrypt.generate_password_hash(pw).decode(),role='owner'); db.session.add(u); db.session.flush(); audit('company_created','company',c.id,{'name':cn}); db.session.commit(); session.clear(); session['user_id']=u.id; return redirect(url_for('dashboard'))
    return page('Register',REG)
@app.route('/login',methods=['GET','POST'])
@limiter.limit('10 per minute')
def login():
    if request.method=='POST':
        u=User.query.filter_by(email=request.form.get('email','').strip().lower()).first()
        if not u or not bcrypt.check_password_hash(u.password_hash,request.form.get('password','')): flash('Invalid credentials.'); return page('Login',LOGIN)
        session.clear(); session['user_id']=u.id; u.last_login_at=utc(); audit('login','user',u.id); db.session.commit(); return redirect(url_for('dashboard'))
    return page('Login',LOGIN)
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))
@app.route('/dashboard')
@login_required
def dashboard():
    c=company(); os_=Opportunity.query.filter_by(company_id=c.id).order_by(Opportunity.estimated.desc()).all(); pipe=sum(o.estimated for o in os_ if o.status in ('OPEN','IN_PROGRESS','PARTIAL')); rec=sum(o.recovered for o in os_); rate=(rec/pipe*100 if pipe else 0); open_=sum(o.status in ('OPEN','IN_PROGRESS','PARTIAL') for o in os_)
    brief=ai(f'Give a 4-bullet executive revenue recovery brief. Open items: {open_}. Estimated recovery pipeline: {money(pipe)}. Recovered revenue: {money(rec)}. Do not invent facts.') if os.getenv('OPENAI_API_KEY') else f'{open_} open opportunities represent {money(pipe)} of estimated recovery. Recovered revenue recorded: {money(rec)}.'
    return page('Dashboard',DASH,os=os_,s={'pipeline':pipe,'recovered':rec,'rate':min(rate,100),'open':open_},brief=brief,money=money)
@app.route('/opportunity/new',methods=['GET','POST'])
@login_required
def new():
    if request.method=='POST':
        c=company(); o=Opportunity(company_id=c.id,customer=request.form.get('customer','').strip(),kind=request.form.get('kind','Other'),priority=request.form.get('priority','MEDIUM'),amount=fnum(request.form.get('amount')),estimated=fnum(request.form.get('estimated')),owner=request.form.get('owner','').strip(),due_date=request.form.get('due_date','').strip(),notes=enc(request.form.get('notes','')),source='manual')
        if not o.customer: flash('Customer required.'); return page('New',NEW)
        db.session.add(o); db.session.flush(); audit('opportunity_created','opportunity',o.id,{'estimated':o.estimated}); db.session.commit(); return redirect(url_for('opp',oid=o.id))
    return page('New',NEW)
@app.route('/opportunity/<int:oid>')
@login_required
def opp(oid):
    o=Opportunity.query.filter_by(id=oid,company_id=company().id).first_or_404(); msg=session.pop('message',''); return page('Opportunity',OPP,o=o,notes=dec(o.notes),message=msg,money=money)
@app.route('/opportunity/<int:oid>/update',methods=['POST'])
@login_required
def update(oid):
    o=Opportunity.query.filter_by(id=oid,company_id=company().id).first_or_404(); old={'status':o.status,'recovered':o.recovered}; o.status=request.form.get('status',o.status); o.recovered=max(0,fnum(request.form.get('recovered'),o.recovered)); o.owner=request.form.get('owner','').strip(); o.due_date=request.form.get('due_date','').strip(); o.notes=enc(request.form.get('notes',''))
    if o.recovered>0 and o.status=='OPEN': o.status='PARTIAL'
    if o.estimated>0 and o.recovered>=o.estimated: o.status='RECOVERED'
    audit('opportunity_updated','opportunity',o.id,{'old':old,'new':{'status':o.status,'recovered':o.recovered}}); db.session.commit()
    try: send_events(company().id,'revenue_recovery.updated',{'opportunity_id':o.id,'customer':o.customer,'status':o.status,'recovered':o.recovered})
    except Exception: pass
    return redirect(url_for('opp',oid=o.id))
@app.route('/opportunity/<int:oid>/draft',methods=['POST'])
@login_required
@limiter.limit('20 per hour')
def draft_route(oid):
    o=Opportunity.query.filter_by(id=oid,company_id=company().id).first_or_404()
    try: session['message']=draft(o); audit('ai_message_drafted','opportunity',o.id); db.session.commit()
    except Exception as e: session['message']='AI error: '+str(e)[:160]
    return redirect(url_for('opp',oid=oid))
@app.route('/import',methods=['GET','POST'])
@login_required
@limiter.limit('20 per hour')
def import_csv():
    if request.method=='POST':
        f=request.files.get('file'); c=company()
        if not f or not f.filename.lower().endswith('.csv'): flash('Upload a CSV.'); return page('Import',IMPORT)
        raw=f.read()
        if len(raw)>10_000_000: flash('CSV too large.'); return page('Import',IMPORT)
        try:
            n=0
            for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
                customer=(r.get('customer') or r.get('customer_id') or '').strip()
                if not customer: continue
                db.session.add(Opportunity(company_id=c.id,customer=customer,kind=(r.get('kind') or r.get('opportunity_type') or 'Imported Risk'),priority=(r.get('priority') or 'MEDIUM').upper(),amount=fnum(r.get('amount')),estimated=fnum(r.get('estimated') or r.get('estimated_recovery')),owner=(r.get('owner') or '').strip(),due_date=(r.get('due_date') or '').strip(),notes=enc(r.get('notes') or ''),source='csv')); n+=1
            audit('csv_import','company',c.id,{'rows':n}); db.session.commit(); flash(f'Imported {n} opportunities.'); return redirect(url_for('dashboard'))
        except Exception as e: db.session.rollback(); flash('Import failed: '+str(e)[:160])
    return page('Import',IMPORT)
@app.route('/integrations',methods=['GET','POST'])
@login_required
@roles('owner','admin')
def integrations():
    c=company()
    if request.method=='POST':
        ep=request.form.get('endpoint','').strip()
        if urlparse(ep).scheme!='https': flash('Webhook endpoint must use HTTPS.'); return page('Integrations',INT,items=Integration.query.filter_by(company_id=c.id).all())
        i=Integration(company_id=c.id,name=request.form.get('name','').strip(),endpoint=enc(ep),secret=enc(request.form.get('secret','')),kind='webhook'); db.session.add(i); db.session.flush(); audit('integration_created','integration',i.id,{'name':i.name}); db.session.commit(); return redirect(url_for('integrations'))
    return page('Integrations',INT,items=Integration.query.filter_by(company_id=c.id).all())
@app.route('/audit')
@login_required
@roles('owner','admin')
def audit(): return page('Audit',AUD,logs=Audit.query.filter_by(company_id=company().id).order_by(Audit.created_at.desc()).limit(300).all())
@app.route('/api/webhooks/<int:cid>/<provider>',methods=['POST'])
@csrf.exempt
@limiter.limit('120 per minute')
def webhook(cid,provider):
    i=Integration.query.filter_by(company_id=cid,active=True,kind='webhook').first_or_404(); raw=request.get_data(); sig=request.headers.get('X-BusinessOS-Signature',''); secret=dec(i.secret)
    if not hmac.compare_digest(sig,signed(secret,raw)): abort(401)
    try:p=request.get_json(force=True)
    except: abort(400)
    eid=str(p.get('event_id') or p.get('id') or '')
    if not eid: abort(400)
    if WebhookEvent.query.filter_by(company_id=cid,provider=provider,event_id=eid).first(): return jsonify(ok=True,duplicate=True)
    db.session.add(WebhookEvent(company_id=cid,provider=provider,event_id=eid,payload_hash=hashlib.sha256(raw).hexdigest())); db.session.commit(); return jsonify(ok=True)
@app.route('/health')
def health():
    try: db.session.execute(db.text('SELECT 1')); return jsonify(status='ok')
    except: return jsonify(status='degraded'),503
@app.errorhandler(403)
def e403(e): return page('Forbidden','<div class="card"><h1>403</h1><p class="muted">Not authorized.</p></div>'),403
@app.errorhandler(429)
def e429(e): return page('Rate limited','<div class="card"><h1>429</h1><p class="muted">Too many requests.</p></div>'),429
with app.app_context(): db.create_all()
if __name__=='__main__': app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG','0')=='1' 