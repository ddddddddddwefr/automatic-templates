# Generators/stubs.py
def to_csharp(result: dict) -> str:
    label = result["label"]
    return f'''// Autogen helper
public static class Router {{
  public static string RouteTicket(dynamic ticket) {{
    var label = "{label}";
    return label == "billing" ? "BillingQueue" : $"{{label}}Queue";
  }}
}}'''


def to_js(result: dict) -> str:
    label = result["label"]
    return f'''export function routeTicket(ticket) {{
  const label = "{label}";
  return label === "billing" ? "BillingQueue" : label + "Queue";
}}'''


