"""Offline extractor registry for reviewed SRD 5.1 patterns.

This deliberately extracts a small, auditable sample set from existing JSON.
Unrecognized or ambiguous input fails; it never fills gaps with generated rules.
"""
import json
import re
from uuid import uuid4
from pathlib import Path
from ruleforge.catalog.models import parse_record
from ruleforge.catalog.service import CatalogService
from ruleforge.rules.sources import SourceReference
from ruleforge.ingestion.evidence import checked_file, contained, digest_text, EvidenceError, now
from ruleforge.ingestion.tables import table_grid

EXTRACTORS = {}

def extractor(category):
    def register(fn):
        if category in EXTRACTORS:
            raise ValueError('duplicate extractor')
        EXTRACTORS[category] = fn
        return fn
    return register

def clean(text):
    return ' '.join(text.replace('*','').split())

def one(values, label):
    values = list(values)
    if len(values) != 1:
        raise EvidenceError(f'{label}: expected one match, found {len(values)}')
    return values[0]

class ExtractionContext:
    def __init__(self, root, run_id):
        self.root = Path(root)
        self.manifest = json.loads(contained(self.root, f'data/runs/{run_id}/manifest.json').read_text(encoding='utf-8'))
        if self.manifest['id'] != run_id or self.manifest.get('ruleset') != 'srd-5.1':
            raise EvidenceError('unsupported ruleset or run identity')
        for ref in [self.manifest['document'], self.manifest['raw'], *self.manifest['artifacts']]:
            checked_file(self.root,ref)
        self.raw = json.loads(checked_file(self.root,self.manifest['raw']).read_text(encoding='utf-8-sig'))
        if self.raw.get('code') != 200:
            raise EvidenceError('unsuccessful raw parse')
        self.elements = self.raw['data']['elements']

    def find(self, predicate, label):
        return one((i for i,e in enumerate(self.elements) if predicate(e)), label)

    def text(self, index):
        return self.elements[index]['text']

    def reference(self, index, role='rule_text', cell=None):
        e = self.elements[index]
        pointer = f'/data/elements/{index}'
        page = e.get('page_number')
        footers = [(i,x) for i,x in enumerate(self.elements) if x.get('page_number') == page
                   and x.get('type') == 'Footer' and x.get('text','').strip().isdigit()]
        footer = footers[0] if len(footers)==1 and page is not None else None
        # xParse's own title ancestry; no inferred page/section numbering.
        from ruleforge.ingestion.provenance import section_hierarchy
        return SourceReference(id=f'{self.manifest["id"]}:element:{index}' + (f':r{cell["row"]}c{cell["column"]}' if cell else ''),
            document_id=self.manifest['document']['sha256'],run_id=self.manifest['id'],role=role,
            fragment_type=e['type'],json_pointer=pointer+'/text',element_pointer=pointer,element_id=e['element_id'],
            section_hierarchy=section_hierarchy(self.raw, e['element_id']),
            page_pointer=pointer+'/page_number' if page is not None else None, physical_page=page,
            printed_page=footer[1]['text'].strip() if footer else None,
            printed_page_pointer=f'/data/elements/{footer[0]}/text' if footer else None,
            quote=e['text'],quote_sha256=digest_text(e['text']),coordinates=e.get('coordinates'),
            table_location={k:cell[k] for k in ('row','column','text')} if cell else None)

    def table_row(self, name, width):
        matches=[]
        for i,e in enumerate(self.elements):
            if e['type'] != 'Table':
                continue
            for row in table_grid(e['text']):
                if len(row)==width and row[0]['text']==name and row[1]['text']:
                    matches.append((i,row))
        return one(matches, 'table row '+name)

    def candidate(self, category, slug, name, payload, sources, fields=None):
        sources = list({s.id:s for s in sources}.values())
        ids = [s.id for s in sources]
        record_id = f'srd51.{category}.{slug}'
        if category == 'equipment':
            payload.update(id=record_id,canonical_name=name,display_name=name,source_ids=ids)
        data = dict(id=record_id,record_type=category,canonical_name=name,source_ids=ids,
                    extraction_run_id=self.manifest['id'],normalized_payload=payload,
                    field_sources=fields or {key:ids for key in payload if key not in ('id','source_ids')})
        return parse_record(data), sources

def money(text):
    match = re.fullmatch(r'([0-9,]+(?:\.[0-9]+)?)\s*(cp|sp|ep|gp|pp)',text)
    if not match:
        raise EvidenceError('unsupported cost '+text)
    return dict(amount=match[1].replace(',',''),unit=match[2])

def weight(text):
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*lb\.',text)
    if not match:
        raise EvidenceError('unsupported weight '+text)
    return dict(amount=match[1],unit='lb')

def duration(text):
    match=re.fullmatch(r'(\d+) (minute|action)s?',text)
    if not match:
        raise EvidenceError('unsupported don/doff time')
    return dict(amount=int(match[1]),unit=match[2])

@extractor('equipment')
def equipment(ctx):
    i,row=ctx.table_row('Dagger',5)
    header=ctx.find(lambda e:e['type']=='Table' and 'Simple Melee Weapons' in e['text'], 'simple melee category')
    # The header and body must be adjacent tables, allowing page footers between them.
    if any(e['type'] not in ('Footer',) for e in ctx.elements[header+1:i]):
        raise EvidenceError('weapon category continuation ambiguous')
    text=[c['text'] for c in row]
    damage=one(re.findall(r'(\d+d\d+) (\w+)',text[2]),'weapon damage')
    props=[]; ranges={}
    for prop in text[4].lower().split(','):
        prop=prop.strip()
        match=re.fullmatch(r'thrown \(range (\d+)/(\d+)\)',prop)
        if match:
            props.append('thrown'); ranges=dict(normal_range=int(match[1]),long_range=int(match[2]))
        elif prop in ('finesse','light'):
            props.append(prop)
        else:
            raise EvidenceError('unreviewed dagger property '+prop)
    yield ctx.candidate('equipment','dagger','Dagger',dict(equipment_type='weapon',description=' | '.join(text),
        cost=money(text[1]),weight=weight(text[3]),proficiency_category='simple',attack_category='melee',
        damage_dice={'expression':damage[0]},damage_type=damage[1],weapon_properties=props,**ranges),
        [ctx.reference(i,'weapon_table',row[0]),ctx.reference(header,'weapon_category')])
    timings=ctx.find(lambda e:e['type']=='Table' and '<td>Doff</td>' in e['text'],'don/doff table')
    times=table_grid(ctx.text(timings))
    for name,category,policy in [('Leather','light','full'),('Chain shirt','medium','capped'),('Chain mail','heavy','none')]:
        i,row=ctx.table_row(name,6); text=[c['text'] for c in row]
        ac=re.sub(r'[\s$]','',text[2])
        pattern={'full':r'(\d+)\+Dexmodifier','capped':r'(\d+)\+Dexmodifier\(max2\)','none':r'(\d+)'}[policy]
        match=re.fullmatch(pattern,ac)
        if not match:
            raise EvidenceError('unsupported armor AC')
        description=ctx.find(lambda e:e['type']=='NarrativeText' and clean(e['text']).startswith(name.title()+'.'),name+' description')
        strategy=ctx.find(lambda e: ('If you wear light armor, you add your Dexterity modifier' in e['text']) if category=='light'
            else ('If you wear medium armor, you add your Dexterity modifier' in e['text']) if category=='medium'
            else ("Heavy armor doesn't let you add your Dexterity modifier" in e['text']), category+' strategy')
        t=one((r for r in times if r[0]['text']==category.title()+' Armor'),'armor timing')
        if text[3]!='-' and not re.fullmatch(r'Str \d+',text[3]):
            raise EvidenceError('unknown strength requirement')
        if text[4] not in ('-','Disadvantage'):
            raise EvidenceError('unknown stealth value')
        yield ctx.candidate('equipment',name.lower().replace(' ','-'),name,dict(equipment_type='armor',
            description=ctx.text(description),cost=money(text[1]),weight=weight(text[5]),armor_category=category,
            base_ac=int(match[1]),dexterity_modifier_policy=policy,dexterity_modifier_cap=2 if policy=='capped' else None,
            strength_requirement=int(text[3].split()[1]) if text[3]!='-' else None,
            stealth_disadvantage=text[4]=='Disadvantage',don_time=duration(t[1]['text']),doff_time=duration(t[2]['text'])),
            [ctx.reference(i,'armor_table',row[0]),ctx.reference(description),ctx.reference(strategy),ctx.reference(timings,'armor_timing',t[0])])
    i,row=ctx.table_row('Shield',6); text=[c['text'] for c in row]
    desc=ctx.find(lambda e:e['text'].startswith('**Shields.**'),'shield description')
    t=one((r for r in times if r[0]['text']=='Shield'),'shield timing')
    if not re.fullmatch(r'\+\d+',text[2]):
        raise EvidenceError('unsupported shield bonus')
    yield ctx.candidate('equipment','shield','Shield',dict(equipment_type='shield',description=ctx.text(desc),
        cost=money(text[1]),weight=weight(text[5]),ac_bonus=int(text[2]),
        equipment_requirements=[ctx.text(desc)],don_time=duration(t[1]['text']),doff_time=duration(t[2]['text'])),
        [ctx.reference(i,'shield_table',row[0]),ctx.reference(desc),ctx.reference(timings,'armor_timing',t[0])])
    i,row=ctx.table_row('Torch',3); text=[c['text'] for c in row]
    desc=ctx.find(lambda e:e['text'].startswith('**Torch.**'),'torch description')
    yield ctx.candidate('equipment','torch','Torch',dict(equipment_type='adventuring_gear',
        description=ctx.text(desc),cost=money(text[1]),weight=weight(text[2]),usage_description=ctx.text(desc)),
        [ctx.reference(i,'gear_table',row[0]),ctx.reference(desc)])

@extractor('spell')
def spell(ctx):
    start=ctx.find(lambda e:e['type']=='Title' and e['text']=='Magic Missile','spell title')
    end=next(i for i in range(start+1,len(ctx.elements)) if ctx.elements[i]['type']=='Title')
    indices=list(range(start,end)); texts=[clean(ctx.text(i)) for i in indices]
    level=one(re.findall(r'(\d)(?:st|nd|rd|th)-level (\w+)',texts[1]),'spell level/school')
    def field(label):
        return one((t.split(':',1)[1].strip() for t in texts if t.startswith(label+':')),label)
    components=field('Components')
    if components.replace(' ','')!='V,S':
        raise EvidenceError('unreviewed spell components')
    description=one((i for i in indices if ctx.text(i).startswith('You create three glowing darts')),'spell effects')
    higher=one((i for i in indices if clean(ctx.text(i)).startswith('At Higher Levels.')),'higher levels')
    damage=one(re.findall(r'(\d+d\d+\s*\+\s*\d+) (force) damage',ctx.text(description)),'spell damage')
    source=ctx.reference(description)
    yield ctx.candidate('spell','magic-missile','Magic Missile',dict(level=int(level[0]),school=level[1],
        casting_time=field('Casting Time'),range=field('Range'),components=dict(verbal=True,somatic=True,material=False),
        duration=field('Duration'),concentration='Concentration' in field('Duration'),ritual='(ritual)' in texts[1],
        description=ctx.text(description),higher_levels=ctx.text(higher),
        effects=[dict(text=ctx.text(description),source_ids=[source.id])],
        damage=[dict(dice={'expression':damage[0].replace(' ','')},damage_type=damage[1],per='dart',source_ids=[source.id])]),
        [ctx.reference(i) for i in indices])

@extractor('class')
def class_record(ctx):
    title=ctx.find(lambda e:e['type']=='Title' and e['text']=='Barbarian','class title')
    cap=ctx.find(lambda e:e['type']=='TableCaption' and clean(e['text'])=='The Barbarian','class table')
    tables=[i for i in range(cap+1,cap+3) if ctx.elements[i]['type']=='Table']
    if len(tables)!=2:
        raise EvidenceError('expected two adjacent barbarian table fragments')
    first,second=[table_grid(ctx.text(i)) for i in tables]
    refs=[ctx.reference(i,'class_progression') for i in tables]
    rows=[]; features=[]
    for number,grid in enumerate((first,second)):
        for row in grid[1:]:
            if len(row)!=5:
                raise EvidenceError('incomplete class table row')
            level=re.fullmatch(r'(\d+)(st|nd|rd|th)',row[0]['text'])
            if not level:
                raise EvidenceError('unrecognized class level')
            cells=[dict(c,source_id=refs[number].id) for c in row]
            names=row[2]['text']
            ids=[refs[number].id]
            if int(level[1])==11:
                continuation=second[0][0]
                if names!='Relentless' or continuation['text']!='Rage' or continuation['colspan']!=5:
                    raise EvidenceError('class continuation requires review')
                names += ' '+continuation['text']
                cells.append(dict(continuation,source_id=refs[1].id));ids.append(refs[1].id)
            names=[x.strip() for x in names.split(',')]
            rows.append(dict(level=int(level[1]),proficiency_bonus=int(row[1]['text']),feature_names=names,cells=cells))
            features.extend(dict(name=name,source_ids=ids) for name in names)
    if [r['level'] for r in rows] != list(range(1,21)):
        raise EvidenceError('incomplete level coverage')
    indices=list(range(title,cap))
    def field(label):
        index=one((i for i in indices if clean(ctx.text(i)).startswith(label+':')),label)
        return clean(ctx.text(index)).split(':',1)[1].strip(),index
    hd,hdi=field('Hit Dice'); die=one(re.findall(r'\b\d+d\d+\b',hd),'hit die')
    proficiency={}; source_indices=[title,title+2,hdi]
    for label,key in [('Armor','armor'),('Weapons','weapons'),('Tools','tools'),('Saving Throws','saving_throws'),('Skills','skills')]:
        value,index=field(label);source_indices.append(index)
        proficiency[key]=[s.strip() for s in value.split(',')] if key=='saving_throws' else value
    yield ctx.candidate('class','barbarian','Barbarian',dict(description=ctx.text(title+2),hit_die={'expression':die},
        proficiencies=proficiency,progression_columns=[c['text'] for c in first[0]],progression=rows,
        feature_references=features),[ctx.reference(i) for i in source_indices]+refs)

@extractor('condition')
def condition(ctx):
    title=ctx.find(lambda e:e['type']=='Title' and e['text']=='Blinded','condition title')
    indices=[]
    for i in range(title+1,len(ctx.elements)):
        if ctx.elements[i]['type']=='Title':
            break
        if ctx.elements[i]['type']=='NarrativeText':
            indices.append(i)
    if len(indices)!=2:
        raise EvidenceError('unexpected blinded effects')
    duration_index=ctx.find(lambda e:e['text'].startswith('A condition lasts either until it is countered'),'condition removal')
    sources=[ctx.reference(i) for i in [title,*indices,duration_index]]
    yield ctx.candidate('condition','blinded','Blinded',dict(description='\n'.join(ctx.text(i) for i in indices),
        effects=[dict(text=ctx.text(i),source_ids=[ctx.reference(i).id]) for i in indices],
        removal_conditions=[ctx.text(duration_index)]),sources)

@extractor('general_rule')
def general_rule(ctx):
    index=ctx.find(lambda e:'subtract 10 from the ability score and then divide the total by 2 (round down)' in e['text'], 'ability modifier')
    source=ctx.reference(index)
    yield ctx.candidate('general_rule','ability-modifier','Ability Scores and Modifiers',dict(category='ability_modifier',
        description=source.quote,resolution_steps=[source.quote],effect_specification=[dict(text=source.quote,source_ids=[source.id])]),[source])

def run_pipeline(root: Path, run_id='srd51-full-001', categories=None, database=None):
    root=Path(root)
    target=root/'data/normalized/m1plus';target.mkdir(parents=True,exist_ok=True)
    report={'normalization_id':uuid4().hex,'run_id':run_id,'started_at':now(),'records':[],'failures':[],
            'review_policy':'All new records require explicit review; none are executable.'}
    try:
        ctx=ExtractionContext(root,run_id)
        service=CatalogService(root,database)
        for category in (categories if categories is not None else EXTRACTORS):
            try:
                if category not in EXTRACTORS:
                    raise EvidenceError('no registered extractor: '+category)
                for record,sources in EXTRACTORS[category](ctx):
                    service.create_candidate(record,sources)
                    validation=service.validate_candidate(record.id,record.record_version)
                    saved=service.get_record(record.id,record.record_version)
                    bundle={'record':saved.model_dump(),'sources':[s.model_dump() for s in sources],'validation':validation}
                    (target/f'{record.id}.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
                    report['records'].append({'id':record.id,'record_type':category,'sources':len(sources),
                        'physical_pages':sorted({s.physical_page for s in sources if s.physical_page is not None}),
                        'review_status':saved.review_status,'execution_status':saved.execution_status})
            except Exception as exc:
                report['failures'].append({'category':category,'error':str(exc),'error_type':type(exc).__name__})
    except Exception as exc:
        report['failures'].append({'category':'input','error':str(exc),'error_type':type(exc).__name__})
    report['status']='failed' if report['failures'] else 'passed'
    report['finished_at']=now()
    encoded = json.dumps(report,ensure_ascii=False,indent=2)
    history = target/'reports'
    history.mkdir(exist_ok=True)
    (history/f'{report["normalization_id"]}.json').write_text(encoded,encoding='utf-8')
    (target/'extraction-report.json').write_text(encoded,encoding='utf-8')
    return report
