'use strict';
var pourOver = angular.module('pourOver', []);

pourOver.controller('LogoutCtrl', ['$scope', '$location', 'Auth', function ($scope, $location, Auth) {
  Auth.logout();
  $location.path('/');
}]);

pourOver.controller('LoginCtrl', ['$scope', '$location', 'Auth', function ($scope, $location, Auth) {
  Auth.login();
  $location.path('/');
}]);

pourOver.config(['$routeProvider', '$locationProvider', function ($routeProvider, $locationProvider) {
  $routeProvider.when('/', {
    templateUrl: '/views/main.html',
    controller: 'MainCtrl',
    auth: true
  });

  $routeProvider.when('/signup/', {
    templateUrl: '/views/signup.html',
  });

  $routeProvider.when('/logout/', {
    controller: 'LogoutCtrl',
    templateUrl: '/views/signup.html',
  });

  $routeProvider.when('/login/', {
    controller: 'LoginCtrl',
    templateUrl: '/views/signup.html',
  });

  $routeProvider.otherwise({
    redirectTo: '/'
  });

  $locationProvider.hashPrefix('#');
  $locationProvider.html5Mode(true);

}]);

pourOver.run(['$rootScope', '$location', 'Auth', function ($rootScope, $location, Auth) {
  // Developers should change this client_id to their own app.
  $rootScope.client_id = '6kmFxf2JrEqmFRQ4WncLfN8WWx7FnUS8';
  $rootScope.redirect_uri = window.location.origin + '/login/';

  $rootScope.$on("$routeChangeStart", function (event, next, current) {
    $rootScope.error = null;
    var loggedIn = Auth.isLoggedIn();
    if (!loggedIn && next.auth) {
      $location.path('/signup');
    }
  });

}]);
