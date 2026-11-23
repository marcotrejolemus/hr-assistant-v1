Feature: Ask the HR Assistant about employees
  HR staff ask questions about employees through a stateless web API.
  A single agent answers using read-only tools over the employee directory.

  Background:
    Given the HR Assistant is running with the fake model

  Scenario: Asking for an existing employee uses get_employee
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer mentions "Jorge Díaz"
    And the tools used are "get_employee"
    And the agent took 2 steps

  Scenario: Asking for an unknown employee says it does not exist
    When I ask "¿Quién es EMP-9999?"
    Then the response status is 200
    And the answer mentions "EMP-9999"
    And the tools used are "get_employee"

  Scenario: Asking for a department lists its people
    When I ask "¿Quiénes trabajan en Finanzas?"
    Then the response status is 200
    And the answer mentions "Sofía Gómez"
    And the tools used are "search_by_department"

  Scenario: A question without an id or department gets the help message
    When I ask "Hola, ¿cómo estás?"
    Then the response status is 200
    And the answer is "Pregúntame por un empleado (EMP-0001) o un departamento."
    And no tools were used
    And the agent took 1 steps

  Scenario: The step cap stops the loop with the fixed message
    Given the agent may take at most 1 steps
    When I ask "¿Quién es EMP-0004?"
    Then the response status is 200
    And the answer is "No pude completar la respuesta. Intenta con una pregunta más concreta."
    And the agent took 1 steps

  Scenario Outline: Invalid questions are rejected
    When I ask a question of <length> characters
    Then the response status is 422

    Examples:
      | length |
      | 0      |
      | 2001   |

  Scenario: The history comes from the client and is not stored
    When I ask "¿Quién es EMP-0004?" with a previous message "Hola"
    And I ask "¿Quién es EMP-0004?" again without history
    Then the response status is 200
    And both answers are the same

  Scenario Outline: Each history message is limited like the question
    When I ask "¿Quién es EMP-0004?" with a previous message of <length> characters
    Then the response status is <status>

    Examples:
      | length | status |
      | 2000   | 200    |
      | 2001   | 422    |

  Scenario: The health check reports the process
    When I check the health endpoint
    Then the response status is 200
    And the health status is "ok" with the process id
