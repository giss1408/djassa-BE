Feature: Deleting an account
  Google Play requires that anyone can delete their account. A customer does
  it in the app, at once. The shop's records stay, but no longer name them.

  Background:
    Given the demo shop is signed in to Fidelia Pro

  Scenario: A customer deletes their account from the app
    Given the customer "07 12 34 56 78" agrees at the counter to collect points
    And the shop records 2 cash sales of 5000 F for that customer
    And the customer signs in to the Fidelia app with "07 12 34 56 78"
    When the customer deletes their account in the app
    Then the shop no longer knows the customer's number
    And the shop still has its 2 sales
    And signing in again with "07 12 34 56 78" opens an empty account

  Scenario: A shop's own number cannot be deleted from the customer app
    When the customer signs in to the Fidelia app with "07 00 00 00 02"
    And the customer deletes their account in the app
    Then the app says to ask from Fidelia Pro
