"""Render Unicode superscripts and subscripts with Matplotlib mathtext."""
import re


SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+-=()ni")
SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ", "0123456789+-=()aehijklmnoprstuvx")


def math_label(text):
    # Preserve existing $...$ expressions, including user-entered formulas.
    parts = re.split(r"(?<!\\)\$", text)
    for index in range(0, len(parts), 2):
        value = re.sub("[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ]+",
                       lambda match: "$^{" + match[0].translate(SUPERSCRIPTS) + "}$", parts[index])
        parts[index] = re.sub("[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ]+",
                              lambda match: "$_{" + match[0].translate(SUBSCRIPTS) + "}$", value)
    return "$".join(parts)
