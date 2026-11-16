"""Order document download names. Stored files and printed identifiers use their own names."""
import hashlib
import re
import unicodedata

from models import db, DocumentTemplate, ExportFilenameSettings

PI_PATTERN = '{PI编号}_{模板名称}'
# Each entry has a label, default rule, available extra fields and preview extension.
DOCUMENTS = {
    'packing-a4': ('完整 A4 装箱单', '{PI编号}_装箱单_第{批次}批', ('批次',), 'pdf'),
    'packing-compact-100x150': ('精简装箱单', '{PI编号}_装箱标签_第{批次}批', ('批次',), 'pdf'),
    'customs': ('报关资料', '{PI编号}_报关资料', (), 'xlsx'),
    'purchase-order': ('采购单', '{PI编号}_采购单_{供应商}', ('供应商',), 'xlsx'),
    'purchase-contract': ('采购合同', '{PI编号}_采购合同_{供应商}', ('供应商',), 'xlsx'),
}
COMMON_FIELDS = ('PI编号', '客户名称', '开单日期', '模板名称')
TOKEN = re.compile(r'\{([^{}]+)\}')
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')
RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)


def settings():
    return db.session.get(ExportFilenameSettings, 1) or ExportFilenameSettings(
        id=1, omit_pi_prefix=True, patterns={})


def definition(code, template_name=''):
    return DOCUMENTS.get(code, (template_name, PI_PATTERN, (), 'pdf'))


def validate_pattern(pattern, extra_fields):
    if not pattern or len(pattern) > 160:
        raise ValueError('请填写 1 至 160 个字符的命名规则。')
    if UNSAFE.search(pattern):
        raise ValueError('规则中含有文件名禁用字符。')
    literal = TOKEN.sub('', pattern)
    if '{' in literal or '}' in literal:
        raise ValueError('请检查字段两侧的花括号。')
    for key in TOKEN.findall(pattern):
        if key not in COMMON_FIELDS + extra_fields:
            raise ValueError(f'此单据不支持字段「{key}」。')
    if not pattern.strip(' .'):
        raise ValueError('文件名不能为空。')
    if pattern.lower().endswith(('.xlsx', '.pdf', '.zip')):
        raise ValueError('扩展名会自动添加，请删除规则末尾的扩展名。')


def safe_filename(stem, extension, suffix=''):
    def clean(value):
        return UNSAFE.sub('_', unicodedata.normalize('NFC', value)).strip(' .')
    stem = clean(stem) or '单据'
    if RESERVED.match(stem):
        stem = '_' + stem
    # Leave room for an extension and for labels on long multibyte filenames.
    suffix = clean(suffix)
    raw_suffix = suffix.encode('utf-8')
    if len(raw_suffix) > 100:
        draft = '-DRAFT' if suffix.endswith('-DRAFT') else ''
        digest = hashlib.sha256(raw_suffix).hexdigest()[:12]
        suffix = raw_suffix[:70].decode('utf-8', 'ignore') + '-' + digest + draft
    budget = 240 - len((suffix + '.' + extension).encode('utf-8'))
    stem = stem.encode('utf-8')[:budget].decode('utf-8', 'ignore').rstrip(' .')
    return f'{stem}{suffix}.{extension}'


def render_name(pattern, omit_prefix, values, extension, suffix=''):
    values = dict(values)
    number = values['PI编号']
    if omit_prefix and number.startswith('PI-') and len(number) > 3:
        values['PI编号'] = number[3:]
    stem = TOKEN.sub(lambda match: str(values.get(match.group(1)) or ''), pattern)
    return safe_filename(stem, extension, suffix)


def order_filename(pi, code, extension, *, template_name='', batch='', supplier='',
                   suffix='', config=None):
    label, default, _, _ = definition(code, template_name)
    config = config or settings()
    values = {
        'PI编号': pi.pi_number, '客户名称': pi.customer.name if pi.customer else '',
        '开单日期': pi.issue_date.isoformat() if pi.issue_date else '',
        '模板名称': template_name or label, '批次': batch, '供应商': supplier,
    }
    return render_name(config.patterns.get(code, default), config.omit_pi_prefix,
                       values, extension, suffix)


def stored_pi_filename(pi, extension):
    # The saved order PDF/workbook is generated as a PI regardless of which
    # editable export template the administrator currently selects by default.
    template = DocumentTemplate.query.filter_by(code='system-default').first()
    return order_filename(pi, 'system-default', extension,
                          template_name=template.name if template else 'PI')
