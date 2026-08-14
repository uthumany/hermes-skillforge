## Description

<!-- Clearly describe what this PR changes and why. Link any related issue. -->

## Type of Change

<!-- Delete options that do not apply -->
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] New format detection (Agent Skills / MCP / plugin / rules / other)
- [ ] Breaking change (fix or feature that would cause existing
      functionality to not work as expected)
- [ ] Documentation update

## How Has This Been Tested?

<!-- Describe the tests you ran to verify your changes. Include command
output where useful. -->

```
python3 -m pytest tests/ -q
python3 scripts/skillforge.py convert <your-test-source>
```

- [ ] Engine suite passes (`10/10`)
- [ ] Sample conversion validates (`VALID`)
- [ ] Generated tests pass

## Checklist

- [ ] My code follows the project's conventions (stdlib-only Python)
- [ ] I have added tests that cover my changes
- [ ] I have updated the relevant reference documentation
- [ ] I have not committed any secrets, tokens, or credentials
