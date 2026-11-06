// DOM-model unit checks for the shipped UI functions; no browser automation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
class Element {
  constructor(tag='div',text=''){this.tag=tag;this.text=text;this.children=[];this.value='';this.checked=true;this.dataset={};this.classes=new Set();this.style={};this.childNodes=[];this.classList={add:x=>this.classes.add(x),remove:x=>this.classes.delete(x),contains:x=>this.classes.has(x),toggle:(x,force)=>{if(force===undefined)force=!this.classes.has(x);force?this.classes.add(x):this.classes.delete(x)}}}
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=[...nodes]}
  set textContent(value){this.text=String(value);this.children=[]}
  get textContent(){return this.text+this.children.map(x=>x instanceof Element?x.textContent:String(x)).join(' ')}
  closest(selector){if(selector==='table')return table;return this}
  querySelector(){return heading}
  scrollIntoView(){}
}
const nodes=new Map(),table=new Element('table'),heading=new Element('th');
const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const el=(tag,text,cls)=>{const node=new Element(tag,text==null?'':String(text));node.className=cls;return node};
const state={personalizedModel:'sector-champion',personalizedLimit:250};
const base={personalized_available:true,personalized_score:.7,personalized_sector_rank:1,personalized_sector_peer_count:2,sector_security_count:2,sector:'Sector',company:'Company',search_aliases:'',result_type:'SECTOR_CHAMPION',evidence_confidence:1,execution_available:false,execution_blocker:'History not verified',review_flags:[],coverage_tier:'FROZEN_SECTOR'};
const old={...base,isin:'OLD',ticker:'OLD',coverage_global_position:1};
const quality={...base,isin:'QUALITY',ticker:'BSE-545020',search_aliases:'BSE:545020 INE1FD201014 Vectras Enprocon',company:'Vectras Enprocon',coverage_global_position:2,personalized_sector_rank:2,coverage_tier:'FUNDAMENTALS_FALLBACK',result_type:'SCREENER_FUNDAMENTALS_FALLBACK',personalized_score:.4};
state.personalized={rows:[old,quality],ranking_scope:'WITHIN_SECTOR',sector_ranked_count:2,coverage:{total_stocks:2,tiers:{FROZEN_SECTOR:1,FUNDAMENTALS_FALLBACK:1},source_as_of_date:'2026-11-06'},as_of_date:'2026-10-03',sector_scoring_note:'Sector positions',execution_boundary:'Execution separate'};
get('personalizedOrder').value='sector';
const context=vm.createContext({console,Node:Element,el,$:get,state,clear:n=>n.replaceChildren(),humanStatus:x=>String(x),pct:x=>x==null?'—':String(x),fmt:x=>x==null?'—':String(x),money:x=>x==null?'Unknown':String(x),compactNumber:x=>String(x),showView:()=>{},runPersonalized:async()=>{},showPersonalizedStock:row=>context.inspected=row});
function install(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);vm.runInContext(source.slice(a,b),context)}
install('function renderPersonalized(){','async function runPersonalized(');
install('async function openChampionStock(','function dashboardSectorTable(');
context.renderPersonalized();
assert.equal(get('personalizedRows').children.length,2);
assert(heading.classList.contains('hidden'));
assert(get('personalizedRows').children[0].children[0].classList.contains('hidden'));
get('personalizedOrder').value='global';context.renderPersonalized();assert(!heading.classList.contains('hidden'));
get('personalizedOrder').value='sector';context.renderPersonalized();
assert.match(get('personalizedCoverageNote').textContent,/1 fundamentals-only proxies/);
assert.match(get('personalizedRows').children[1].children[3].textContent,/2 \/ 2/);
assert.doesNotMatch(get('personalizedRows').textContent,/Ranking unavailable/);
get('personalizedFallbacks').checked=false;context.renderPersonalized();
assert.equal(get('personalizedRows').children.length,1);
assert.match(get('personalizedRows').textContent,/OLD/);
get('personalizedFallbacks').checked=true;
get('personalizedSearch').value='545020';context.renderPersonalized();
assert.equal(get('personalizedRows').children.length,1);
assert.match(get('personalizedRows').textContent,/Vectras/);
get('personalizedSearch').value='';
state.personalized.rows=Array.from({length:5547},(_,i)=>({...old,isin:'ID'+i,ticker:'T'+i,personalized_sector_rank:i+1,personalized_sector_peer_count:5547,coverage_global_position:i+1}));
context.renderPersonalized();assert.equal(get('personalizedRows').children.length,250);
state.personalizedLimit=6000;context.renderPersonalized();assert.equal(get('personalizedRows').children.length,5547);
assert(get('personalizedMore').classList.contains('hidden'));
assert.equal(get('personalizedRows').children.at(-1).children[3].textContent,'5547 / 5547');
state.personalized.rows=[old,quality];
(async()=>{
  // Header search must work before any legacy live-market data is loaded.
  get('terminalSearch').value='BSE:545020';await context.terminalSearch();
  assert.equal(context.inspected.isin,'QUALITY');
  assert.equal(get('personalizedOrder').value,'sector');
  assert.equal(get('personalizedFallbacks').checked,true);
  context.inspected=null;get('terminalSearch').value='Vectras';await context.terminalSearch();assert.equal(context.inspected.isin,'QUALITY');
  context.currentRankingRecovery('dashboardState',new Error('Missing legacy bundle'));
  assert.match(get('dashboardState').textContent,/Open current sector rankings/);
  context.statusItems=(id,items)=>context.latestDetail=items;
  install('function showPersonalizedStock(row){','function renderPersonalized(){');
  context.showPersonalizedStock(quality);assert.equal(context.latestDetail.personalized_sector_position,'2 of 2');
  context.showPersonalizedStock({...quality,personalized_available:false,personalized_score:null});
  assert.equal(context.latestDetail.personalized_sector_position,'2 of 2');
  console.log('PASS: sector positions, fundamentals filter, aliases, header search, all-5547 pagination and archive recovery');
})().catch(error=>{console.error(error);process.exitCode=1});
