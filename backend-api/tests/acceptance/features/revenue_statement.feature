Feature: A revenue statement a lender can trust
  The shop's sales history becomes a signed statement it can show a partner.
  Any change to the figures breaks the signature.

  Background:
    Given the demo shop is signed in to Fidelia Pro
    And the demo shop is on the network plan

  Scenario: The statement verifies, and an inflated one does not
    Given a customer pays the shop 4000 F with Wave
    And the shop records a cash sale of 1500 F
    When the shop downloads its revenue statement
    Then the statement counts 5500 F of turnover
    And the statement names no customer
    And a partner checking the statement finds it genuine
    But a partner checking a copy with the turnover inflated finds it forged
