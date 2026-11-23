Feature: Route each question to a model and report its cost
  A deterministic router sends simple questions to the small model and
  complex ones to the large model. Every answer and the metrics report the
  estimated cost in USD.

  Background:
    Given the HR Assistant is running with the fake model

  Scenario: A simple question goes to the small model and has a cost
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the model used is "@cf/meta/llama-3.1-8b-instruct-fast"
    And the route is "simple"
    And the answer cost is greater than zero
    And no call was cached

  Scenario: A complex question goes to the large model
    When I ask "Compara a los empleados del departamento de Finanzas"
    Then the response status is 200
    And the model used is "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    And the route is "complex_keyword"

  Scenario: The metrics add up the cost of every answer
    When I ask "¿Quién es EMP-0004?"
    And I ask "Compara a los empleados del departamento de Finanzas"
    Then the metrics cost equals the sum of both answers
    And the billed cost is "not_available"
