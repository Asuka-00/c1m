// usage: node audit.js <before|after> [locale...]
const {chromium}=require('playwright');const fs=require('fs');
const API='http://localhost:8000/api/v1', UI='http://localhost:5173';
const phase=process.argv[2]||'before';
const LOCS=process.argv.slice(3).length?process.argv.slice(3):['zh-CN','ja','en'];
const DETECT=()=>{
  const out=[];const W=innerWidth;
  if(document.documentElement.scrollWidth>W+1) out.push({type:'hscroll',el:'html',text:String(document.documentElement.scrollWidth)});
  const vis=e=>{const r=e.getBoundingClientRect();if(r.width<2||r.height<2)return false;const s=getComputedStyle(e);return s.visibility!=='hidden'&&s.display!=='none'&&!e.closest('[aria-hidden=true],.sr-only')};
  const desc=e=>e.tagName.toLowerCase()+(e.dataset.slot?`[${e.dataset.slot}]`:'')+(e.dataset.sidebar?`{${e.dataset.sidebar}}`:'')+(e.id?`#${e.id}`:'');
  const lines=e=>{const w=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);let n,max=0;
    while((n=w.nextNode())){if(!n.textContent.trim())continue;const rg=document.createRange();rg.selectNodeContents(n);
      const fs=parseFloat(getComputedStyle(n.parentElement).fontSize)||14;const tops=[];
      for(const r of rg.getClientRects()){if(r.width<1)continue;if(!tops.some(t=>Math.abs(t-r.top)<fs*0.7))tops.push(r.top)}
      max=Math.max(max,tops.length)}
    return max};
  const txt=e=>(e.innerText||'').trim().replace(/\s+/g,' ').slice(0,60);
  const WRAP='th,label,button,a[data-slot=button],[data-sidebar=menu-button],[data-sidebar=menu-sub-button],[data-slot=badge],[role=tab],[data-slot=select-trigger],[data-slot=dialog-title],[data-slot=card-title],h1';
  const seen=new Set();
  for(const e of document.querySelectorAll(WRAP)){ if(!vis(e)||!txt(e))continue; if(e.closest('[data-audit-ignore]'))continue;
    if(lines(e)>1){out.push({type:'wrap',el:desc(e),text:txt(e)});seen.add(e)}}
  for(const e of document.querySelectorAll(WRAP+',td,[data-slot=select-value],span.truncate,p.truncate,div.truncate')){
    if(!vis(e)||seen.has(e)||!txt(e))continue; if(e.closest('[data-audit-ignore]'))continue;
    if(e.scrollWidth>e.clientWidth+1){const s=getComputedStyle(e);
      if(s.overflowX==='visible'&&s.textOverflow!=='ellipsis'){ // spills out
        if(e.tagName!=='TD') out.push({type:'overflow',el:desc(e),text:txt(e)});
      } else if(!e.closest('[title]')) out.push({type:'truncated',el:desc(e),text:txt(e)});}}
  // any short text (label-like, <= 28 chars) that wraps onto 2+ lines
  {const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
   while((n=w.nextNode())){const tx=n.textContent.trim();if(!tx||tx.length>28)continue;const pe=n.parentElement;
     if(!pe||seen.has(pe)||pe.closest('textarea,[data-audit-ignore],script,style')||!vis(pe))continue;
     const rg=document.createRange();rg.selectNodeContents(n);const fs=parseFloat(getComputedStyle(pe).fontSize)||14;const tops=[];
     for(const r of rg.getClientRects()){if(r.width<1)continue;if(!tops.some(t=>Math.abs(t-r.top)<fs*0.7))tops.push(r.top)}
     if(tops.length>1){seen.add(pe);out.push({type:'wrap',el:desc(pe),text:tx})}}}
  for(const d of document.querySelectorAll('[role=dialog],[role=alertdialog]')){const r=d.getBoundingClientRect();
    if(d.scrollWidth>d.clientWidth+1||r.right>W+1||r.left<-1) out.push({type:'dialog-overflow',el:desc(d),text:txt(d.querySelector('h2')||d)});}
  return out;};
(async()=>{
 const tok=(await (await fetch(API+'/login/access-token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'username=admin&password=admin123'})).json()).access_token;
 const tm=await (await fetch(API+'/tenants/me',{headers:{Authorization:'Bearer '+tok}})).json();
 const H={Authorization:'Bearer '+tok,'X-Tenant-ID':tm.data.find(x=>x.tenant.slug==='default').tenant.id};
 const get=async u=>(await fetch(API+u,{headers:H})).json();
 const menus=(await get('/menus/me')).menus;const paths=[];const walk=a=>{for(const m of a){if(m.path)paths.push(m.path);walk(m.children||[])}};walk(menus);
 const lots=(await get('/mes/lot?page_size=50&sort_by=code&sort_order=asc')).data;
 const L=c=>lots.find(l=>l.code===c)?.id;
 const wo2=(await get('/mes/work-order?q=WO-DEMO-02')).data[0];
 const extra=[`/mes/lot-console?lot=${L('DM26100001')}`,`/mes/lot-console?lot=${L('DM26100003')}`,`/mes/lot-console?lot=${L('DM26100004')}`,`/mes/lot-trace?lot=${L('DM26100001')}`,`/mes/lot-trace?lot=${L('DM26100004')}`,'/settings','/settings/appearance'];
 if(wo2) extra.push(`/mes/lot-start?wo=${wo2.id}`);
 const all=[...new Set([...paths,...extra])];
 const b=await chromium.launch();const report={};
 await Promise.all(LOCS.map(async loc=>{
  const res=report[loc]=[];
  for(const width of [1280,1440]){
   const ctx=await b.newContext({viewport:{width,height:800}});
   await ctx.addInitScript(l=>localStorage.setItem('lang',l),loc);
   const p=await ctx.newPage();const dir=`/workspace/screenshots/ui-audit/${phase}/${loc}`;fs.mkdirSync(dir,{recursive:true});
   const name=s=>s.replace(/^\//,'').replace(/\?.*lot=([0-9a-f]{6}).*/,'_$1').replace(/\?.*/,'').replace(/[^\w-]+/g,'_')||'home';
   const check=async(page,label,shot)=>{await p.waitForTimeout(350);const iss=await p.evaluate(DETECT);
     for(const i of iss) res.push({width,page:label,...i});
     if(shot&&(iss.length||width===1280)) await p.screenshot({path:`${dir}/${name(label)}${shot===true?'':'__'+shot}-${width}.png`});
     return iss.length;};
   await p.goto(UI+'/sign-in',{waitUntil:'networkidle'});await check(0,'/sign-in',true);
   await p.fill('input[name=login]','admin');await p.fill('input[name=password]','admin123');await p.press('input[name=password]','Enter');
   await p.waitForURL(u=>!u.pathname.includes('sign-in'));await p.waitForTimeout(1200);
   // expand every sidebar group
   await p.evaluate(()=>{});
   for(const path of all){
    try{await p.goto(UI+path,{waitUntil:'networkidle',timeout:20000});}catch(e){}
    await p.waitForTimeout(500);
    if(path==='/') { // open all sidebar groups once for sidebar check
      for(const g of await p.locator('[data-sidebar=menu-button][data-state=closed]').all()){try{await g.click({timeout:1000})}catch(e){}}
      await p.waitForTimeout(400);
    }
    await check(0,path,true);
    if(width!==1280) continue;
    // create dialog
    let nb=p.locator('[data-testid=crud-new]');
    if(!(await nb.count())) nb=p.locator('main button:has(svg.lucide-plus)').first();
    if(await nb.count()&&await nb.isVisible().catch(()=>false)){
      try{await nb.click({timeout:2000});await p.waitForSelector('[role=dialog]',{timeout:3000});await check(0,path,'create');}catch(e){}
      await p.keyboard.press('Escape');await p.waitForTimeout(200);
    }
    if(path.includes('lot-console')){
      for(const tid of ['open-split','open-merge','open-hold','open-release']){
        const bt=p.locator(`[data-testid=${tid}]`).first();
        if(await bt.count()&&await bt.isEnabled().catch(()=>false)){try{await bt.click({timeout:2000});await p.waitForSelector('[role=dialog]',{timeout:3000});
          if(tid==='open-split'){const pl=p.locator('[data-testid=child-plus]');if(await pl.count())await pl.click();}
          await check(0,path,tid);}catch(e){}
          await p.keyboard.press('Escape');await p.waitForTimeout(200);}
      }
      const pv=p.locator('[data-testid=preview-stage]').first();
      if(await pv.count()&&await pv.isEnabled().catch(()=>false)){try{await pv.click();await p.waitForTimeout(900);await check(0,path,'checks');}catch(e){}}
    }
   }
   await ctx.close();
  }
 }));
 await b.close();
 fs.writeFileSync(`/workspace/screenshots/ui-audit/${phase}/report.json`,JSON.stringify(report,null,1));
 for(const l of Object.keys(report)){const by={};for(const i of report[l])by[i.type]=(by[i.type]||0)+1;console.log(l,report[l].length,JSON.stringify(by));}
})().catch(e=>{console.error(e);process.exit(1)});
