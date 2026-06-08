import re

with open('main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Fix parameter order: move `session: AsyncSession = Depends(get_db),` to the end of the arguments list.
# We will use regex to find `async def func_name(session: AsyncSession = Depends(get_db), ...)` and move it.

def fix_signature(match):
    func_name = match.group(1)
    # The arguments are between the first paren and the close paren
    # But wait, there could be multiple lines.
    # It's better to just replace `session: AsyncSession = Depends(get_db), ` with nothing
    # and then add it before the closing `):` or just `)`
    pass

# Let's just remove the bad `session: AsyncSession = Depends(get_db), ` insertion
code = code.replace('session: AsyncSession = Depends(get_db), \n    ', '')
code = code.replace('session: AsyncSession = Depends(get_db), ', '')

# And now inject it properly at the end of the argument list for each route
# Routes are decorated with @app.get, @app.post, etc.
# But it's easier to just do it manually for the known functions:
funcs = [
    'v1_plans', 'v1_balance', 'v1_client', 'v1_ledger', 'v1_usage_summary',
    'v1_usage_daily', 'v1_usage_forecast', 'v1_client_set_payee', 'v1_spend',
    'v1_topup', 'v1_paywall_challenge', 'v1_paywall_verify', 'get_ticket', 'dev_mock_pay'
]

for func in funcs:
    # Find `async def func(...):`
    # We can match up to the closing `):` or `) -> ...:`
    pattern = r'(async def ' + func + r'\b[^)]*)(\)\s*(?:->\s*[^:]+)?\s*:)'
    
    def replacer(m):
        args = m.group(1)
        if 'session: AsyncSession = Depends(get_db)' not in args:
            if args.endswith('(') or args.endswith(', ') or args.endswith(','):
                return args + 'session: AsyncSession = Depends(get_db)' + m.group(2)
            else:
                return args + ', session: AsyncSession = Depends(get_db)' + m.group(2)
        return m.group(0)
        
    code = re.sub(pattern, replacer, code)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("fixed")
