import json, logging, os, subprocess
from copy import deepcopy
import salt.utils.dictupdate

__virtualname__ = 'pfsense'
__PFCLI__ = '/usr/local/bin/php-cgi'
oscmd = subprocess.Popen
PIPE = subprocess.PIPE
DEFAULT_PFSENSE_INCLUDES = [
    'globals.inc',
    'functions.inc',
    'config.inc',
    'util.inc'
    ]

log = logging.getLogger(__virtualname__)

def __virtual__():
    '''
    only load if pfsense CLI is available
    '''
    if os.access('/usr/local/sbin/pfSsh.php', os.X_OK):
        IS_PFSENSE = __virtualname__
    else:
        IS_PFSENSE = False
    return IS_PFSENSE

class Script():
    '''
    attributes:
      includes: list of PHP "require_once" include files
      body: list of script lines as strings

    str():
      conversion to string rendes the the script with includes, in PHP tags
    '''
    def __init__(self, *body, **kwargs):
        self.body = []
        if body:
            for arg in body:
                if len(self.body) > 0:
                    self.body.append('')
                self.body += arg.splitlines()
                self.body.append('')
        if 'includes' in kwargs:
            for inc in kwargs['includes']:
                self.includes.append(inc)
        else:
            self.includes = deepcopy(DEFAULT_PFSENSE_INCLUDES)

    def __str__(self):
        PHP_begin = "<?php\n"
        PHP_end = "\n?>"

        _fmt_inc_ = 'require_once("{}");'
        includes_block = "\n".join([_fmt_inc_.format(i) for i in self.includes])
        script_body = "\n" + "\n".join(self.body)
        return PHP_begin + includes_block + "\n" + script_body + PHP_end

def run(php_script):
    '''
    runs a script via pfSense php-cgi CLI and returns a tuple:
      - stdout
      - stderr
    '''
    shell = oscmd([__PFCLI__], stdin=PIPE, stdout=PIPE, stderr=PIPE)

    raw_out, raw_err = shell.communicate(input=str(php_script).encode())
    if raw_out or raw_error:
        log.debug("running commands in php-cgi: \n%s", str(php_script))
    if raw_out:
        log.debug("stdout:\n%s", raw_out)
    if raw_err:
        log.debug("stderr:\n%s", raw_err)

    if raw_out[:13].lower() == 'content-type:': # strip bogus MIME header
        out = b'\n'.join(raw_out.splitlines()[1:])
    else:
        out = b'\n'.join(raw_out.splitlines()[1:])
    return out, raw_err


is_dict = lambda o: 'keys' in dir(o) # duck type check dict
is_str = lambda o: 'decode' in dir(o) # duck type check str
is_seq = lambda o: 'index' in dir(o) and not is_str(o) # duck type check sequence


def get_config(*args):
    '''
    Optionally takes a string argument as colon-delimited config key:
      - if the key is not truth-y (Default None), the whole config is returned
      - if the key is not found in the config, None is returned
      - if the key is found, the matching part of the config is returned

    Key matching supports k=v searching in cases where the config tree is a list
    or the config tree dict uses arbitrary or opaque keys for child objects. If
    a key has a '=' everything preceding and following the first '=' will be
    treated as a k=v match, respectively. The k=v matching searches the list or
    dict for the first child dict like object with a matching k,v pair.

    uses php-cgi CLI to run PHP commands
    returns the pfSense $config nested array structure as native python data

    PHP -> json -> python
    '''
    keys = None
    if len(args) > 1 or (len(args) == 1 and args[0] != str(args[0])):
        raise ValueError('get_config optionally takes only 1 string argument as key')
    else:
        if len(args) == 1:
            keys = args[0].split(':')
    __dump_config_php__ = 'print_r(json_encode($config, $options=JSON_PRETTY_PRINT));'
    get_config_script = Script(__dump_config_php__)
    cmd_out, cmd_err = run(get_config_script)
    pfConfig = json.loads(cmd_out)

    if keys: # iteratively prune the config for the key or return None
        for _k in keys:
            if '=' in _k: # match first
                k, v = _k.split('=',1)
            else:
                k, v = (_k, None)
            ctx_pfConfig = pfConfig
            if v: # the match is a k=v pair
                _kv_match = None
                if is_seq(ctx_pfConfig): # search sequence for matching dict
                    for _node in ctx_pfConfig:
                        if is_dict(_node) and k in _node and _node[k] == v:
                            _kv_match = _node
                            break
                    if _kv_match:
                        pfConfig = _kv_match

                elif is_dict(ctx_pfConfig): # search dict for matching dict
                    for _node_k, _node_v in ctx_pfConfig.iteritems():
                        if is_dict(_node_v) and k in _node_v and _node_v[k] == v:
                            _kv_match = _node_v
                            break

                if not _kv_match:
                    _nomatch_debug_lines = [
                        "no match for '{}={}' found in config context:",
                        "'{}'",
                        " ... using:",
                        "'{}'"
                        ]
                    _nomatch_debug_tmpl = '\n'.join(_nomatch_debug_lines)
                    _debug_msg = _nomatch_debug_tmpl.format(k,v,repr(ctx_pfConfig), args[0])
                    log.debug(_debug_msg)
                    pfConfig = None
                    break
            else:
                if k in ctx_pfConfig:
                    pfConfig = ctx_pfConfig[k]
                else:
                    log.debug("no config key match for '{}' using '{}'".format(k, args[0]))
                    pfConfig = None

    del get_config_script
    return pfConfig


def _reduced_config_diff(orig_config, changed_config):
    '''
    takes two args: orig_config, changed_config
    returns: difference between changed_config and orig_config

    Walks dict and sequence like objects and returns those parts of changed_config
    not matching the corresponding key/index of orig_config
    '''
    if is_dict(orig_config) and is_dict(changed_config):
        for k in changed_config.keys():
            if k in orig_config and changed_config[k] == orig_config[k]:
                log.garbage('%s == %s', repr(changed_config[k]), repr(orig_config[k]))
                log.garbage('removing %s from config diff', k)
                del(changed_config[k])
            else:
                changed_config[k] = _reduced_config_diff(orig_config[k], changed_config[k])
    if is_seq(orig_config) and is_seq(changed_config):
        for i in range(len(changed_config)):
            if 'keys' in dir(changed_config[i]):
                changed_config[i] = _reduced_config_diff(orig_config[i], changed_config[i])
    return changed_config

# https://gist.github.com/josephj/5028375
__php_array_merge_recursive_distinct_func__ = '''
function array_merge_recursive_distinct(array &$array1, array &$array2)
{
    $merged = $array1;
    foreach ($array2 as $key => &$value)
    {
        if (is_array($value) && isset($merged[$key]) && is_array($merged[$key]))
        {
            $merged[$key] = array_merge_recursive_distinct($merged[$key], $value);
        }
        else
        {
            $merged[$key] = $value;
        }
    }
    return $merged;
}
'''

__php_recursive_array_diff_func__ = '''
function array_diff_assoc_recursive ( )
{
    $args = func_get_args ( );
    $diff = array ( );
    foreach ( array_shift ( $args ) as $key => $val )
    {
        for ( $i = 0, $j = 0, $tmp = array ( $val ) , $count = count ( $args ); $i < $count; $i++ )
            if ( is_array ( $val ) )
                if ( !isset ( $args[$i][$key] ) || !is_array ( $args[$i][$key] ) || empty( $args[$i][$key] ) )
                    $j++;
                else
                    $tmp[] = $args[$i][$key];
            elseif ( ! array_key_exists ( $key, $args[$i] ) || $args[$i][$key] !== $val )
                $j++;
        if ( is_array ( $val ) )
        {
            $tmp = call_user_func_array ( __FUNCTION__, $tmp );
            if ( ! empty ( $tmp ) ) $diff[$key] = $tmp;
            elseif ( $j == $count ) $diff[$key] = $val;
        }
        elseif ( $j == $count && $count ) $diff[$key] = $val;
    }

    return $diff;
}
'''

def _php_config_editscript(changes, desc='salt execution'):
    '''
    takes one arg: changes

    returns Script() object to effect those changes
    '''
    changes = deepcopy(changes)
    script = Script()
    jcs = json.JSONEncoder().encode(changes)
    script.body.append(__php_array_merge_recursive_distinct_func__)
    script.body.append(__php_recursive_array_diff_func__)
    script.body.append("$new_configs = json_decode('{}', true);".format(jcs))
    script.body.append("parse_config(true);")
    script.body.append("$orig_config = $config;")
    script.body.append("$config = array_merge_recursive_distinct($config, $new_configs);")
    script.body.append('$config = write_config($desc="{}");'.format(desc))
    script.body.append('\nif ($config != false) {')
    script.body.append('  print_r(json_encode(array_diff_assoc_recursive($orig_config, $config), $options=JSON_PRETTY_PRINT));')
    script.body.append('}\n')
    log.debug("generated php edit script: \n%s", str(script))

    return script


def set_config(pfConfig, test=False):
    '''
    takes an argument: a partial pfSense config structure

    merges the target config into the pfSense config, and reloads
    '''
    prior_pfConfig = get_config()
    tgt_pfConfig = deepcopy(prior_pfConfig)
    # walk the pfConfig and perform a deep merge on the tgt_pfConfig
    tgt_pfConfig = salt.utils.dictupdate.update(tgt_pfConfig, pfConfig)
    changes = _reduced_config_diff(prior_pfConfig, tgt_pfConfig)
    if not changes:
        changes = None
    log.debug('changes for pfsense config: %s', repr(changes))

    edit_config = _php_config_editscript(changes)
    if not test:
        run(edit_config)
