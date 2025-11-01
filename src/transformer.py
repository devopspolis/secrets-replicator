"""
Transformation engine for secret values.

Supports two transformation modes:
1. Sed-style regex replacements (line-by-line)
2. JSON field mappings (JSONPath-based)
"""

import json
import re
import signal
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from jsonpath_ng import parse as jsonpath_parse


# Exceptions
class TransformationError(Exception):
    """Raised when transformation fails"""
    pass


class RegexTimeoutError(TransformationError):
    """Raised when regex execution times out"""
    pass


class InvalidRegexError(TransformationError):
    """Raised when regex pattern is invalid"""
    pass


class InvalidJsonError(TransformationError):
    """Raised when JSON parsing fails"""
    pass


# Data classes
@dataclass
class SedRule:
    """Represents a sed-style transformation rule"""
    pattern: str
    replacement: str
    flags: int = 0
    global_replace: bool = False

    def __post_init__(self):
        """Validate the regex pattern"""
        try:
            re.compile(self.pattern, self.flags)
        except re.error as e:
            raise InvalidRegexError(f"Invalid regex pattern '{self.pattern}': {e}")


@dataclass
class JsonMapping:
    """Represents a JSON field transformation"""
    path: str           # JSONPath expression
    find: str          # Value to find
    replace: str       # Replacement value

    def __post_init__(self):
        """Validate the JSONPath expression"""
        try:
            jsonpath_parse(self.path)
        except Exception as e:
            raise TransformationError(f"Invalid JSONPath '{self.path}': {e}")


# Sed-style transformations
def parse_sedfile(content: str) -> List[SedRule]:
    """
    Parse sed-style transformation rules from text content.

    Format:
        s/pattern/replacement/[flags]
        # Comments are ignored
        Empty lines are ignored

    Flags:
        g - Global replacement (replace all occurrences, not just first)
        i - Case-insensitive matching

    Args:
        content: Text content containing sed rules

    Returns:
        List of SedRule objects

    Raises:
        InvalidRegexError: If a regex pattern is invalid
        TransformationError: If sed rule format is invalid

    Examples:
        >>> rules = parse_sedfile("s/us-east-1/us-west-2/g")
        >>> rules[0].pattern
        'us-east-1'
        >>> rules[0].replacement
        'us-west-2'
        >>> rules[0].global_replace
        True
    """
    rules = []

    for line_num, line in enumerate(content.split('\n'), 1):
        # Strip whitespace
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue

        # Parse sed command: s/pattern/replacement/[flags]
        if not line.startswith('s/'):
            raise TransformationError(
                f"Line {line_num}: Sed rule must start with 's/' - got '{line[:20]}...'"
            )

        # Remove 's/' prefix
        line = line[2:]

        # Find delimiter (usually /, but could be others)
        # We'll use / as the delimiter for simplicity
        parts = line.split('/')

        if len(parts) < 2:
            raise TransformationError(
                f"Line {line_num}: Invalid sed format - expected 's/pattern/replacement/[flags]'"
            )

        pattern = parts[0]
        replacement = parts[1]
        flags_str = parts[2] if len(parts) > 2 else ''

        # Parse flags
        re_flags = 0
        global_replace = False

        for flag in flags_str:
            if flag == 'g':
                global_replace = True
            elif flag == 'i':
                re_flags |= re.IGNORECASE
            elif flag == 'm':
                re_flags |= re.MULTILINE
            elif flag == 's':
                re_flags |= re.DOTALL
            elif flag:  # Ignore empty string but warn on unknown flags
                # In production, you might want to log a warning here
                pass

        rules.append(SedRule(
            pattern=pattern,
            replacement=replacement,
            flags=re_flags,
            global_replace=global_replace
        ))

    return rules


def _timeout_handler(signum, frame):
    """Signal handler for regex timeout"""
    raise RegexTimeoutError("Regex execution timed out (possible ReDoS attack)")


def apply_sed_transforms(
    secret_value: str,
    rules: List[SedRule],
    timeout_seconds: int = 5
) -> str:
    """
    Apply sed-style regex transformations to secret value.

    Args:
        secret_value: Original secret value (string)
        rules: List of SedRule objects to apply
        timeout_seconds: Maximum time to spend on each regex (prevents ReDoS)

    Returns:
        Transformed secret value

    Raises:
        RegexTimeoutError: If regex execution exceeds timeout
        TransformationError: If transformation fails

    Examples:
        >>> rules = [SedRule(pattern='us-east-1', replacement='us-west-2')]
        >>> apply_sed_transforms('db.us-east-1.aws.com', rules)
        'db.us-west-2.aws.com'
    """
    transformed = secret_value

    for rule in rules:
        try:
            # Compile regex
            regex = re.compile(rule.pattern, rule.flags)

            # Set timeout alarm (Unix only - won't work on Windows)
            # For Lambda (Linux), this provides ReDoS protection
            try:
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(timeout_seconds)

                # Apply transformation
                if rule.global_replace:
                    transformed = regex.sub(rule.replacement, transformed)
                else:
                    transformed = regex.sub(rule.replacement, transformed, count=1)

                # Cancel alarm
                signal.alarm(0)
            except AttributeError:
                # signal.SIGALRM not available (Windows) - apply without timeout
                # In production Lambda (Linux), this won't happen
                if rule.global_replace:
                    transformed = regex.sub(rule.replacement, transformed)
                else:
                    transformed = regex.sub(rule.replacement, transformed, count=1)

        except RegexTimeoutError:
            raise
        except re.error as e:
            raise TransformationError(
                f"Regex error in pattern '{rule.pattern}': {e}"
            ) from e
        except Exception as e:
            raise TransformationError(
                f"Unexpected error applying rule '{rule.pattern}': {e}"
            ) from e

    return transformed


# JSON transformations
def parse_json_mapping(content: str) -> List[JsonMapping]:
    """
    Parse JSON transformation mappings from JSON content.

    Format:
        {
          "transformations": [
            {
              "path": "$.database.host",
              "find": "db1.us-east-1",
              "replace": "db1.us-west-2"
            }
          ]
        }

    Args:
        content: JSON content containing transformation mappings

    Returns:
        List of JsonMapping objects

    Raises:
        InvalidJsonError: If JSON is invalid
        TransformationError: If mapping format is invalid
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise InvalidJsonError(f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise TransformationError("JSON must be an object with 'transformations' array")

    if 'transformations' not in data:
        raise TransformationError("JSON must contain 'transformations' array")

    if not isinstance(data['transformations'], list):
        raise TransformationError("'transformations' must be an array")

    mappings = []

    for idx, mapping_dict in enumerate(data['transformations']):
        if not isinstance(mapping_dict, dict):
            raise TransformationError(
                f"Transformation {idx}: must be an object"
            )

        # Validate required fields
        required_fields = ['path', 'find', 'replace']
        for field in required_fields:
            if field not in mapping_dict:
                raise TransformationError(
                    f"Transformation {idx}: missing required field '{field}'"
                )

        mappings.append(JsonMapping(
            path=mapping_dict['path'],
            find=mapping_dict['find'],
            replace=mapping_dict['replace']
        ))

    return mappings


def apply_json_transforms(
    secret_value: str,
    mappings: List[JsonMapping]
) -> str:
    """
    Apply JSON path-based transformations to secret value.

    Args:
        secret_value: Original secret value (JSON string)
        mappings: List of JsonMapping objects to apply

    Returns:
        Transformed secret value (JSON string)

    Raises:
        InvalidJsonError: If secret value is not valid JSON
        TransformationError: If transformation fails

    Examples:
        >>> secret = '{"db": {"host": "db1.us-east-1"}}'
        >>> mappings = [JsonMapping(path='$.db.host', find='us-east-1', replace='us-west-2')]
        >>> apply_json_transforms(secret, mappings)
        '{"db":{"host":"db1.us-west-2"}}'
    """
    try:
        secret_obj = json.loads(secret_value)
    except json.JSONDecodeError as e:
        raise InvalidJsonError(f"Secret value is not valid JSON: {e}") from e

    for mapping in mappings:
        try:
            # Parse JSONPath expression
            jsonpath_expr = jsonpath_parse(mapping.path)

            # Find all matches
            matches = jsonpath_expr.find(secret_obj)

            if not matches:
                # Path not found - this is not necessarily an error
                # Just skip this transformation
                continue

            # Update matching values
            for match in matches:
                current_value = match.value

                # Only replace if current value matches 'find'
                if isinstance(current_value, str) and current_value == mapping.find:
                    # Update the value
                    jsonpath_expr.update(secret_obj, mapping.replace)
                elif isinstance(current_value, str) and mapping.find in current_value:
                    # Partial match - replace substring
                    new_value = current_value.replace(mapping.find, mapping.replace)
                    jsonpath_expr.update(secret_obj, new_value)

        except Exception as e:
            raise TransformationError(
                f"Error applying JSONPath '{mapping.path}': {e}"
            ) from e

    # Return JSON string (compact format, no extra whitespace)
    return json.dumps(secret_obj, separators=(',', ':'))


# Convenience function for mode selection
def transform_secret(
    secret_value: str,
    mode: str,
    rules_content: str,
    is_binary: bool = False
) -> str:
    """
    Transform secret value using specified mode.

    Args:
        secret_value: Original secret value
        mode: Transformation mode ('sed' or 'json')
        rules_content: Transformation rules (sedfile or JSON mapping)
        is_binary: Whether secret is binary (binary secrets are not transformed)

    Returns:
        Transformed secret value

    Raises:
        TransformationError: If transformation fails
        ValueError: If mode is invalid
    """
    if is_binary:
        # Don't transform binary secrets
        return secret_value

    if mode == 'sed':
        rules = parse_sedfile(rules_content)
        return apply_sed_transforms(secret_value, rules)
    elif mode == 'json':
        mappings = parse_json_mapping(rules_content)
        return apply_json_transforms(secret_value, mappings)
    else:
        raise ValueError(f"Invalid transformation mode: {mode}. Must be 'sed' or 'json'")
