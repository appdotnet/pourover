'use strict';
var pourOver = angular.module('pourOver', ['adn', 'angular-markdown', 'ui']);

pourOver.controller('LogoutCtrl', ['$scope', '$location', 'Auth', function ($scope, $location, Auth) {
  Auth.logout();
  $location.path('/');
}]);

pourOver.controller('LoginCtrl', ['$scope', '$location', 'Auth', function ($scope, $location, Auth) {
  Auth.login();
  $location.path('/');
}]);

pourOver.config(['$routeProvider', '$locationProvider', 'ADNConfigProvider', function ($routeProvider, $locationProvider, ADNConfigProvider) {
  $routeProvider.when('/', {
    templateUrl: '/views/main.html',
    controller: 'MainCtrl',
    auth: true
  });

  $routeProvider.when('/feed/:feed_type/:feed_id/', {
    templateUrl: '/views/feed_detail.html',
    controller: 'FeedDetailCtrl',
    auth: true
  });

  $routeProvider.when('/alerts_xyx/', {
    templateUrl: '/views/channel_list.html',
    controller: 'BroadcastChannelListCtrl',
    auth: true
  });

  $routeProvider.when('/alerts_xyx/new/', {
    templateUrl: '/views/new-channel.html',
    controller: 'NewChannelCtrl',
    auth: true
  });

  $routeProvider.when('/alerts_xyx/:channel_id/', {
    templateUrl: '/views/channel.html',
    controller: 'ChannelCtrl'
  });


  $routeProvider.when('/alerts/', {
    redirectTo: function () {
      window.location = 'https://directory.app.net/alerts/manage/';
    },
    auth: false,
  });

  $routeProvider.when('/alerts/new/', {
    redirectTo: function () {
      window.location = 'https://directory.app.net/alerts/manage/create/';
    },
    auth: false,
  });

  $routeProvider.when('/alerts/:channel_id/', {
    redirectTo: function (params) {
      window.location  = 'https://directory.app.net/alerts/manage/' + params.channel_id + '/';
    },
    auth: false,
  });

  $routeProvider.when('/signup/', {
    templateUrl: '/views/signup.html',
    auth: false,
  });

  $routeProvider.when('/logout/', {
    controller: 'LogoutCtrl',
    templateUrl: '/views/signup.html',
  });

  $routeProvider.when('/login/instagram/', {
    controller: 'InstagramCtrl',
    templateUrl: '/views/instagram_signup.html',
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

// Create an AngularJS service called debounce
pourOver.factory('debounce', ['$timeout','$q', function($timeout, $q) {
  // The service is actually this function, which we call with the func
  // that should be debounced and how long to wait in between calls
  return function debounce (func, wait, immediate) {
    var timeout;
    // Create a deferred object that will be resolved when we need to
    // actually call the func
    var deferred = $q.defer();
    return function () {
      var context = this, args = arguments;
      var later = function() {
        timeout = null;
        if(!immediate) {
          deferred.resolve(func.apply(context, args));
          deferred = $q.defer();
        }
      };
      var callNow = immediate && !timeout;
      if ( timeout ) {
        $timeout.cancel(timeout);
      }
      timeout = $timeout(later, wait);
      if (callNow) {
        deferred.resolve(func.apply(context,args));
        deferred = $q.defer();
      }
      return deferred.promise;
    };
  };
}]);

pourOver.run(['$rootScope', '$location', 'Auth', 'LocalUser', function ($rootScope, $location, Auth, LocalUser) {
  // Developers should change this client_id to their own app.
  $rootScope.client_id = '6kmFxf2JrEqmFRQ4WncLfN8WWx7FnUS8';
  $rootScope.instagram_client_id = 'e13ece0f2a574acc8a8d404e3330a6e4';
  $rootScope.redirect_uri = window.location.origin + '/login/';
  $rootScope.instagram_redirect_uri = window.location.origin + '/login/instagram/';
  // Try and log the user in
  Auth.login();

  if ($location.search().no_header) {
    jQuery('.nav.header').hide();
  }

  $rootScope.$on('$routeChangeStart', function (event, next) {
    $rootScope.error = null;
    var loggedIn = Auth.isLoggedIn();
    if (!loggedIn && next.auth) {
      if (window.location.pathname === '/') {
        $location.path('/signup');
      } else {
        window.location = 'https://account.app.net/oauth/authenticate?client_id='+$rootScope.client_id+'&response_type=token&scope=write_post+messages+public_messages&redirect_uri=' + window.location;
      }
    }
  });

}]);
