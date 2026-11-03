# Unit Conversions Reference

Standard conversions for recipe regionalisation.

## Temperature

| Gas Mark | Celsius | Fahrenheit | Description |
|----------|---------|------------|-------------|
| ¼ | 110°C | 225°F | Very cool |
| ½ | 120°C | 250°F | Very cool |
| 1 | 140°C | 275°F | Cool |
| 2 | 150°C | 300°F | Cool |
| 3 | 160°C | 325°F | Moderately cool |
| 4 | 180°C | 350°F | Moderate |
| 5 | 190°C | 375°F | Moderately hot |
| 6 | 200°C | 400°F | Hot |
| 7 | 220°C | 425°F | Hot |
| 8 | 230°C | 450°F | Very hot |
| 9 | 240°C | 475°F | Very hot |
| 10 | 260°C | 500°F | Extremely hot |

### Quick Conversion

**Celsius to Fahrenheit:** °F = (°C × 9/5) + 32  
**Fahrenheit to Celsius:** °C = (°F - 32) × 5/9

## Weight

| Metric | Imperial |
|--------|----------|
| 15g | ½ oz |
| 25g | 1 oz |
| 50g | 2 oz |
| 75g | 3 oz |
| 100g | 3½ oz |
| 150g | 5 oz |
| 200g | 7 oz |
| 250g | 9 oz |
| 300g | 10½ oz |
| 350g | 12 oz |
| 400g | 14 oz |
| 450g | 1 lb |
| 500g | 1 lb 2 oz |
| 750g | 1 lb 10 oz |
| 1 kg | 2 lb 4 oz |

### Quick Conversion

**Grams to ounces:** oz = g × 0.035  
**Ounces to grams:** g = oz × 28.35

## Volume

### Liquid

| Metric | Imperial | US Cups |
|--------|----------|---------|
| 30ml | 1 fl oz | ⅛ cup |
| 60ml | 2 fl oz | ¼ cup |
| 90ml | 3 fl oz | ⅓ cup |
| 120ml | 4 fl oz | ½ cup |
| 150ml | 5 fl oz (¼ pint) | ⅔ cup |
| 180ml | 6 fl oz | ¾ cup |
| 240ml | 8 fl oz | 1 cup |
| 300ml | 10 fl oz (½ pint) | 1¼ cups |
| 450ml | 15 fl oz (¾ pint) | 2 cups |
| 600ml | 20 fl oz (1 pint) | 2½ cups |
| 1 litre | 35 fl oz | 4¼ cups |

### Spoons

| Metric | UK/US | Australia |
|--------|-------|-----------|
| 5ml | 1 tsp | 1 tsp |
| 15ml | 1 tbsp | ¾ tbsp |
| 20ml | 1⅓ tbsp | 1 tbsp |

**Note:** Australian tablespoons are 20ml, not 15ml.

## Common Ingredients by Volume to Weight

For recipes that use cups, approximate weight conversions:

| Ingredient | 1 Cup | Notes |
|------------|-------|-------|
| All-purpose flour | 125g | Spooned, levelled |
| Bread flour | 130g | |
| Sugar (granulated) | 200g | |
| Sugar (brown, packed) | 220g | |
| Sugar (powdered) | 120g | |
| Butter | 225g | 2 sticks |
| Rice (uncooked) | 185g | |
| Oats | 90g | |
| Honey | 340g | |
| Milk | 245g | |
| Cream | 235g | |
| Yogurt | 245g | |
| Grated cheese | 100g | |

## Pan Sizes

| Description | Metric | Imperial |
|-------------|--------|----------|
| Small | 20cm | 8 inch |
| Medium | 23cm | 9 inch |
| Large | 25cm | 10 inch |
| Loaf tin | 23 × 13cm | 9 × 5 inch |
| Square tin | 20cm | 8 inch |
| Baking tray | 33 × 23cm | 13 × 9 inch |

## Conversion Functions

### For Scripts

```python
def celsius_to_fahrenheit(c):
    return (c * 9/5) + 32

def fahrenheit_to_celsius(f):
    return (f - 32) * 5/9

def grams_to_oz(g):
    return g * 0.03527

def oz_to_grams(oz):
    return oz * 28.35

def ml_to_cups(ml):
    return ml / 240

def cups_to_ml(cups):
    return cups * 240
```

### Gas Mark Lookup

```python
GAS_MARKS = {
    0.25: (110, 225),
    0.5: (120, 250),
    1: (140, 275),
    2: (150, 300),
    3: (160, 325),
    4: (180, 350),
    5: (190, 375),
    6: (200, 400),
    7: (220, 425),
    8: (230, 450),
    9: (240, 475),
    10: (260, 500),
}

def gas_to_celsius(gas):
    return GAS_MARKS.get(gas, (180, 350))[0]

def gas_to_fahrenheit(gas):
    return GAS_MARKS.get(gas, (180, 350))[1]
```
