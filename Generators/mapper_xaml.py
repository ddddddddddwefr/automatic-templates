# Generators/mapper_xaml.py
import uuid


def to_xaml(result: dict) -> str:
    label = result["label"]
    return f'''<Activity x:Class="Autogen_{uuid.uuid4().hex}"
 xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
 xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
 xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence>
    <ui:LogMessage Level="Info" Text="Auto-generated route: {label}" />
    <If>
      <If.Condition>[="{label}"="billing"]</If.Condition>
      <If.Then>
        <ui:LogMessage Level="Info" Text="Send to Billing Queue" />
      </If.Then>
      <If.Else>
        <ui:LogMessage Level="Info" Text="Send to {label} Queue" />
      </If.Else>
    </If>
  </Sequence>
</Activity>'''


